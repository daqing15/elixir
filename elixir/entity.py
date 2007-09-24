'''
Entity baseclass, metaclass and descriptor
'''

import sqlalchemy

from sqlalchemy                     import Table, Integer, String, desc,\
                                           ForeignKey, and_
from sqlalchemy.orm                 import deferred, Query, MapperExtension,\
                                           mapper, object_session
from sqlalchemy.ext.sessioncontext  import SessionContext
from sqlalchemy.util                import OrderedDict

from elixir.statements              import Statement
from elixir.fields                  import Field
from elixir.options                 import options_defaults


try:
    set
except NameError:
    from sets import Set as set

import sys
import warnings

import elixir
import inspect

__pudge_all__ = ['Entity', 'EntityMeta']

DEFAULT_AUTO_PRIMARYKEY_NAME = "id"
DEFAULT_AUTO_PRIMARYKEY_TYPE = Integer
DEFAULT_VERSION_ID_COL = "row_version"
DEFAULT_POLYMORPHIC_COL_NAME = "row_type"
DEFAULT_POLYMORPHIC_COL_SIZE = 40
DEFAULT_POLYMORPHIC_COL_TYPE = String(DEFAULT_POLYMORPHIC_COL_SIZE)

try: 
    from sqlalchemy.orm import ScopedSession
except ImportError: 
    # Not on sqlalchemy version 0.4
    ScopedSession = type(None)
    
def _do_mapping(session, cls, *args, **kwargs):
    if session is None:
        return mapper(cls, *args, **kwargs)
    elif isinstance(session, ScopedSession):
        return session.mapper(cls, *args, **kwargs)
    elif isinstance(session, SessionContext):
        extension = kwargs.pop('extension', None)
        if extension is not None:
            if not isinstance(extension, list):
                extension = [extension]
            extension.append(session.mapper_extension)
        else:
            extension = session.mapper_extension

        class query(object):
            def __getattr__(s, key):
                return getattr(session.registry().query(cls), key)
            def __call__(s):
                return session.registry().query(cls)

        if not 'query' in cls.__dict__: 
            cls.query = query()

        return mapper(cls, extension=extension, *args, **kwargs)

class EntityDescriptor(object):
    '''
    EntityDescriptor describes fields and options needed for table creation.
    '''
    
    def __init__(self, entity):
        entity.table = None
        entity.mapper = None

        self.entity = entity
        self.module = sys.modules[entity.__module__]

        self.has_pk = False

        self.parent = None
        self.children = []

        for base in entity.__bases__:
            if issubclass(base, Entity) and base is not Entity:
                if self.parent:
                    raise Exception('%s entity inherits from several entities,'
                                    ' and this is not supported.' 
                                    % self.entity.__name__)
                else:
                    self.parent = base
                    self.parent._descriptor.children.append(entity)

        self.fields = OrderedDict()
        self.relationships = list()
        self.delayed_properties = dict()
        self.constraints = list()

        # set default value for options
        self.order_by = None
        self.table_args = list()
        self.metadata = getattr(self.module, 'metadata', elixir.metadata)
        self.session = getattr(self.module, 'session', elixir.session)

        for option in ('inheritance', 'polymorphic',
                       'autoload', 'tablename', 'shortnames', 
                       'auto_primarykey', 'version_id_col'):
            setattr(self, option, options_defaults[option])

        for option_dict in ('mapper_options', 'table_options'):
            setattr(self, option_dict, options_defaults[option_dict].copy())
 
    def setup_options(self):
        '''
        Setup any values that might depend on using_options. For example, the 
        tablename or the metadata.
        '''
        elixir.metadatas.add(self.metadata)

        objectstore = None
        session = self.session
        if session is None or isinstance(session, ScopedSession):
            # no stinking objectstore
            pass
        elif isinstance(session, SessionContext):
            objectstore = Objectstore(session)
        elif not hasattr(session, 'registry'):
            # Both SessionContext and ScopedSession have a registry attribute,
            # but objectstores (whether Elixir's or Activemapper's) don't, so 
            # if we are here, it means an Objectstore is used for the session.
            objectstore = session
            session = objectstore.context

        self.session = session
        self.objectstore = objectstore

        entity = self.entity
        if self.inheritance == 'concrete' and self.polymorphic:
            raise NotImplementedError("Polymorphic concrete inheritance is "
                                      "not yet implemented.")

        if self.parent:
            if self.inheritance == 'single':
                self.tablename = self.parent._descriptor.tablename

        if not self.tablename:
            if self.shortnames:
                self.tablename = entity.__name__.lower()
            else:
                modulename = entity.__module__.replace('.', '_')
                tablename = "%s_%s" % (modulename, entity.__name__)
                self.tablename = tablename.lower()
        elif callable(self.tablename):
            self.tablename = self.tablename(entity)

    def setup_autoload_table(self):
        self.setup_table(True)

    def create_pk_cols(self):
        """
        Create primary_key columns. That is, add columns from belongs_to
        relationships marked as being a primary_key and then add a primary 
        key to the table if it hasn't already got one and needs one. 
        
        This method is "semi-recursive" in that it calls the create_keys 
        method on BelongsTo relationships and those in turn call create_pk_cols
        on their target. It shouldn't be possible to have an infinite loop 
        since a loop of primary_keys is not a valid situation.
        """
        for rel in self.relationships:
            rel.create_keys(True)

        if not self.autoload:
            if self.parent and self.inheritance == 'multi':
                # add foreign keys to the parent's primary key columns 
                parent_desc = self.parent._descriptor
                for pk_col in parent_desc.primary_keys:
                    colname = "%s_%s" % (self.parent.__name__.lower(),
                                         pk_col.key)

                    # it seems like SA ForeignKey is not happy being given a 
                    # real column object when said column is not yet attached 
                    # to a table
                    pk_col_name = "%s.%s" % (parent_desc.tablename, pk_col.key)
                    field = Field(pk_col.type, ForeignKey(pk_col_name), 
                                  colname=colname, primary_key=True)
                    self.add_field(field)
            if not self.has_pk and self.auto_primarykey:
                #FIXME: we'll need to do a special case for concrete 
                # inheritance too
                if self.parent and self.inheritance == 'single':
                    return

                if isinstance(self.auto_primarykey, basestring):
                    colname = self.auto_primarykey
                else:
                    colname = DEFAULT_AUTO_PRIMARYKEY_NAME
                
                self.add_field(Field(DEFAULT_AUTO_PRIMARYKEY_TYPE,
                                     colname=colname, primary_key=True))

    def setup_relkeys(self):
        for rel in self.relationships:
            rel.create_keys(False)

    def before_table(self):
        Statement.process(self.entity, 'before_table')
        
    def setup_table(self, only_autoloaded=False):
        '''
        Create a SQLAlchemy table-object with all columns that have been 
        defined up to this point.
        '''
        if self.entity.table:
            return

        if self.autoload != only_autoloaded:
            return
        
        if self.parent:
            if self.inheritance == 'single':
                # we know the parent is setup before the child
                self.entity.table = self.parent.table 

                # re-add the entity fields to the parent entity so that they
                # are added to the parent's table (whether the parent's table
                # is already setup or not).
                for field in self.fields.itervalues():
                    self.parent._descriptor.add_field(field)
                for constraint in self.constraints:
                    self.parent._descriptor.add_constraint(constraint)
                return
            elif self.inheritance == 'concrete':
               # copy all fields from parent table
               for field in self.parent._descriptor.fields.itervalues():
                    self.add_field(field.copy())
               #FIXME: copy constraints. But those are not as simple to copy
               #since the source column must be changed

        if self.polymorphic and self.inheritance in ('single', 'multi') and \
           self.children and not self.parent:
            if not isinstance(self.polymorphic, basestring):
                self.polymorphic = DEFAULT_POLYMORPHIC_COL_NAME
                
            self.add_field(Field(DEFAULT_POLYMORPHIC_COL_TYPE, 
                                 colname=self.polymorphic))

        if self.version_id_col:
            if not isinstance(self.version_id_col, basestring):
                self.version_id_col = DEFAULT_VERSION_ID_COL
            self.add_field(Field(Integer, colname=self.version_id_col))

        # create list of columns and constraints
        args = [field.column for field in self.fields.itervalues()] \
                    + self.constraints + self.table_args
        
        # specify options
        kwargs = self.table_options

        if self.autoload:
            kwargs['autoload'] = True

        self.entity.table = Table(self.tablename, self.metadata, 
                                  *args, **kwargs)

    def setup_reltables(self):
        for rel in self.relationships:
            rel.create_tables()

    def after_table(self):
        Statement.process(self.entity, 'after_table')

    def setup_events(self):
        def make_proxy_method(methods):
            def proxy_method(self, mapper, connection, instance):
                for func in methods:
                    func(instance)
            return proxy_method

        # create a list of callbacks for each event
        methods = {}
        for name, func in inspect.getmembers(self.entity, inspect.ismethod):
            if hasattr(func, '_elixir_events'):
                for event in func._elixir_events:
                    event_methods = methods.setdefault(event, [])
                    event_methods.append(func)
        
        if not methods:
            return
        
        # transform that list into methods themselves
        for event in methods:
            methods[event] = make_proxy_method(methods[event])
        
        # create a custom mapper extension class, tailored to our entity
        ext = type('EventMapperExtension', (MapperExtension,), methods)()
        
        # then, make sure that the entity's mapper has our mapper extension
        self.add_mapper_extension(ext)

    def before_mapper(self):
        Statement.process(self.entity, 'before_mapper')

    def _get_children(self):
        children = self.children[:]
        for child in self.children:
            children.extend(child._descriptor._get_children())
        return children

    def evaluate_property(self, prop):
        if callable(prop):
            return prop(self.entity.table.c)
        else:
            return prop

    def translate_order_by(self, order_by):
        if isinstance(order_by, basestring):
            order_by = [order_by]
        
        order = list()
        for field in order_by:
            col = self.fields[field.strip('-')].column
            if field.startswith('-'):
                col = desc(col)
            order.append(col)
        return order

    def setup_mapper(self):
        '''
        Initializes and assign an (empty!) mapper to the entity.
        '''
        if self.entity.mapper:
            return
        
        kwargs = self.mapper_options
        if self.order_by:
            kwargs['order_by'] = self.translate_order_by(self.order_by)
        
        if self.version_id_col:
            kwargs['version_id_col'] = self.fields[self.version_id_col].column

        if self.inheritance in ('single', 'concrete', 'multi'):
            if self.parent and \
               not (self.inheritance == 'concrete' and not self.polymorphic):
                kwargs['inherits'] = self.parent.mapper

            if self.inheritance == 'multi' and self.parent:
                col_pairs = zip(self.primary_keys,
                                self.parent._descriptor.primary_keys)
                kwargs['inherit_condition'] = \
                    and_(*[pc == c for c,pc in col_pairs])

            if self.polymorphic:
                if self.children and not self.parent:
                    kwargs['polymorphic_on'] = \
                        self.fields[self.polymorphic].column
                    #TODO: this is an optimization, and it breaks the multi
                    # table polymorphic inheritance test with a relation. 
                    # So I turn it off for now. We might want to provide an 
                    # option to turn it on.
#                    if self.inheritance == 'multi':
#                        children = self._get_children()
#                        join = self.entity.table
#                        for child in children:
#                            join = join.outerjoin(child.table)
#                        kwargs['select_table'] = join
                    
                if self.children or self.parent:
                    #TODO: make this customizable (both callable and string)
                    #TODO: include module name
                    kwargs['polymorphic_identity'] = \
                        self.entity.__name__.lower()

                if self.inheritance == 'concrete':
                    kwargs['concrete'] = True

        properties = dict()
        for field in self.fields.itervalues():
            if field.deferred:
                group = None
                if isinstance(field.deferred, basestring):
                    group = field.deferred
                properties[field.column.name] = deferred(field.column,
                                                         group=group)

        for name, prop in self.delayed_properties.iteritems():
            properties[name] = self.evaluate_property(prop)
        self.delayed_properties.clear()

        if 'primary_key' in kwargs:
            cols = self.entity.table.c
            kwargs['primary_key'] = [getattr(cols, colname) for
                colname in kwargs['primary_key']]

        if self.parent and self.inheritance == 'single':
            args = []
        else:
            args = [self.entity.table]

        self.entity.mapper = _do_mapping(self.session, self.entity, 
                                         properties=properties,
                                         *args, **kwargs)

    def after_mapper(self):
        Statement.process(self.entity, 'after_mapper')

    def setup_properties(self):
        for rel in self.relationships:
            rel.create_properties()

    def finalize(self):
        Statement.process(self.entity, 'finalize')

    #--------------

    def add_field(self, field):
#        if field.colname in self.fields:
#            print "duplicate field", field.colname
        self.fields[field.colname] = field
        
        if field.primary_key:
            self.has_pk = True

        # we don't want to trigger setup_all too early
        table = type.__getattribute__(self.entity, 'table')
        if table:
#TODO: we might want to check for that case
#            if field.colname in table.columns.keys():
            table.append_column(field.column)
    
    def add_constraint(self, constraint):
        self.constraints.append(constraint)
        
        table = self.entity.table
        if table:
            table.append_constraint(constraint)
        
    def add_property(self, name, prop):
        if self.entity.mapper:
            prop_value = self.evaluate_property(prop)
            self.entity.mapper.add_property(name, prop_value)
        else:
            self.delayed_properties[name] = prop
    
    def add_mapper_extension(self, extension):
        extensions = self.mapper_options.get('extension', [])
        if not isinstance(extensions, list):
            extensions = [extensions]
        extensions.append(extension)
        self.mapper_options['extension'] = extensions

    def get_inverse_relation(self, rel, reverse=False):
        '''
        Return the inverse relation of rel, if any, None otherwise.
        '''

        matching_rel = None
        for other_rel in self.relationships:
            if other_rel.is_inverse(rel):
                if matching_rel is None:
                    matching_rel = other_rel
                else:
                    raise Exception(
                            "Several relations match as inverse of the '%s' "
                            "relation in entity '%s'. You should specify "
                            "inverse relations manually by using the inverse "
                            "keyword."
                            % (rel.name, rel.entity.__name__))
        # When a matching inverse is found, we check that it has only
        # one relation matching as its own inverse. We don't need the result
        # of the method though. But we do need to be careful not to start an
        # infinite recursive loop.
        if matching_rel and not reverse:
            rel.entity._descriptor.get_inverse_relation(matching_rel, True)

        return matching_rel

    def find_relationship(self, name):
        for rel in self.relationships:
            if rel.name == name:
                return rel
        if self.parent:
            return self.parent.find_relationship(name)
        else:
            return None

    def primary_keys(self):
        if self.autoload:
            return [col for col in self.entity.table.primary_key.columns]
        else:
            if self.parent and self.inheritance == 'single':
                return self.parent._descriptor.primary_keys
            else:
                return [field.column for field in self.fields.itervalues() if
                        field.primary_key]
    primary_keys = property(primary_keys)


class TriggerProxy(object):
    """A class that serves as a "trigger" ; accessing its attributes runs
    the function that is set at initialization.

    Primarily used for setup_all().

    Note that the `setupfunc` parameter is called on each access of
    the attribute.

    """
    def __init__(self, class_, attrname, setupfunc):
        self.class_ = class_
        self.attrname = attrname
        self.setupfunc = setupfunc

    def __getattr__(self, name):
        self.setupfunc()
        proxied_attr = getattr(self.class_, self.attrname)
        return getattr(proxied_attr, name)

    def __repr__(self):
        proxied_attr = getattr(self.class_, self.attrname)
        return "<TriggerProxy (%s)>" % (self.class_.__name__)

def _is_entity(class_):
    return isinstance(class_, EntityMeta)

class EntityMeta(type):
    """
    Entity meta class. 
    You should only use this if you want to define your own base class for your
    entities (ie you don't want to use the provided 'Entity' class).
    """
    _ready = False
    _entities = {}

    def __init__(cls, name, bases, dict_):
        # only process subclasses of Entity, not Entity itself
        if bases[0] is object:
            return

        # build a dict of entities for each frame where there are entities
        # defined
        caller_frame = sys._getframe(1)
        cid = cls._caller = id(caller_frame)
        caller_entities = EntityMeta._entities.setdefault(cid, {})
        caller_entities[name] = cls

        # Append all entities which are currently visible by the entity. This 
        # will find more entities only if some of them where imported from 
        # another module.
        for entity in [e for e in caller_frame.f_locals.values() 
                         if _is_entity(e)]:
            caller_entities[entity.__name__] = entity

        # create the entity descriptor
        desc = cls._descriptor = EntityDescriptor(cls)

        # process statements. Needed before the proxy for metadata
        Statement.process(cls)

        # Process attributes, for the assignment syntax.
        cls._process_attrs(dict_)

        # setup misc options here (like tablename etc.)
        desc.setup_options()

        # create trigger proxies
        # TODO: support entity_name... or maybe not. I'm not sure it makes 
        # sense in Elixir.
        cls._setup_proxy()

    def _setup_proxy(cls, entity_name=None):
        #TODO: move as much as possible of those "_private" values to the
        # descriptor, so that we don't mess the initial class.
        cls._class_key = sqlalchemy.orm.mapperlib.ClassKey(cls, entity_name)

        tablename = cls._descriptor.tablename
        schema = cls._descriptor.table_options.get('schema', None)
        cls._table_key = sqlalchemy.schema._get_table_key(tablename, schema)

        elixir._delayed_entities.append(cls)
        
        mapper_proxy = TriggerProxy(cls, 'mapper', elixir.setup_all)
        table_proxy = TriggerProxy(cls, 'table', elixir.setup_all)

        sqlalchemy.orm.mapper_registry[cls._class_key] = mapper_proxy
        md = cls._descriptor.metadata
        md.tables[cls._table_key] = table_proxy

        # We need to monkeypatch the metadata's table iterator method because 
        # otherwise it doesn't work if the setup is triggered by the 
        # metadata.create_all().
        # This is because ManyToMany relationships add tables AFTER the list 
        # of tables that are going to be created is "computed" 
        # (metadata.tables.values()).
        # see:
        # - table_iterator method in MetaData class in sqlalchemy/schema.py 
        # - visit_metadata method in sqlalchemy/ansisql.py
        original_table_iterator = md.table_iterator
        if not hasattr(original_table_iterator, 
                       '_non_elixir_patched_iterator'):
            def table_iterator(*args, **kwargs):
                elixir.setup_all()
                return original_table_iterator(*args, **kwargs)
            table_iterator.__doc__ = original_table_iterator.__doc__
            table_iterator._non_elixir_patched_iterator = \
                original_table_iterator
            md.table_iterator = table_iterator

        cls._ready = True

    def _process_attrs(cls, attr_dict):
        """Process class attributes, looking for Elixir `Field`s or
        `Relationship`.
        """

        for name, attr in attr_dict.iteritems():
            # Check if it's Elixir related. 
            if isinstance(attr, Field):
                # If no colname was defined (through the 'colname' kwarg), set
                # it to the name of the attr.
                if attr.colname is None:
                    attr.colname = name
                cls._descriptor.add_field(attr)
            elif isinstance(attr, elixir.relationships.Relationship):
                attr.name = name 
                attr.entity = cls
                cls._descriptor.relationships.append(attr)
            else:
                # Not an Elixir field, let it be. 
                pass
        return

    def __getattribute__(cls, name):
        if type.__getattribute__(cls, "_ready"):
            #TODO: we need to add all assign_mapper methods
            if name in ('c', 'table', 'mapper'):
                elixir.setup_all()
        return type.__getattribute__(cls, name)

    def __call__(cls, *args, **kwargs):
        elixir.setup_all()
        return type.__call__(cls, *args, **kwargs)



class Entity(object):
    '''
    The base class for all entities
    
    All Elixir model objects should inherit from this class. Statements can
    appear within the body of the definition of an entity to define its
    fields, relationships, and other options.
    
    Here is an example:

    ::
    
        class Person(Entity):
            has_field('name', Unicode(128))
            has_field('birthdate', DateTime, default=datetime.now)
    
    Please note, that if you don't specify any primary keys, Elixir will
    automatically create one called ``id``.
    
    For further information, please refer to the provided examples or
    tutorial.
    '''
    __metaclass__ = EntityMeta

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    # session methods
    def flush(self, *args, **kwargs):
        return object_session(self).flush([self], *args, **kwargs)

    def delete(self, *args, **kwargs):
        return object_session(self).delete(self, *args, **kwargs)

    def expire(self, *args, **kwargs):
        return object_session(self).expire(self, *args, **kwargs)

    def refresh(self, *args, **kwargs):
        return object_session(self).refresh(self, *args, **kwargs)

    def expunge(self, *args, **kwargs):
        return object_session(self).expunge(self, *args, **kwargs)

    # This bunch of session methods, along with all the query methods below 
    # only make sense when using a global/scoped/contextual session.
    def _global_session(self):
        return self._descriptor.session.registry()
    _global_session = property(_global_session)

    def merge(self, *args, **kwargs):
        return self._global_session.merge(self, *args, **kwargs)

    def save(self, *args, **kwargs):
        return self._global_session.save(self, *args, **kwargs)

    def update(self, *args, **kwargs):
        return self._global_session.update(self, *args, **kwargs)

    def save_or_update(self, *args, **kwargs):
        return self._global_session.save_or_update(self, *args, **kwargs)

    # query methods
    def get_by(cls, *args, **kwargs):
        return cls.query.filter_by(*args, **kwargs).first()
    get_by = classmethod(get_by)

    def get(cls, *args, **kwargs):
        return cls.query.get(*args, **kwargs)
    get = classmethod(get)

    #-----------------#
    # DEPRECATED LAND #
    #-----------------#

    def filter(cls, *args, **kwargs):
        warnings.warn("The filter method on the class is deprecated."
                      "You should use cls.query.filter(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter(*args, **kwargs)
    filter = classmethod(filter)

    def filter_by(cls, *args, **kwargs):
        warnings.warn("The filter_by method on the class is deprecated."
                      "You should use cls.query.filter_by(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter_by(*args, **kwargs)
    filter_by = classmethod(filter_by)

    def select(cls, *args, **kwargs):
        warnings.warn("The select method on the class is deprecated."
                      "You should use cls.query.filter(...).all()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter(*args, **kwargs).all()
    select = classmethod(select)

    def select_by(cls, *args, **kwargs):
        warnings.warn("The select_by method on the class is deprecated."
                      "You should use cls.query.filter_by(...).all()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter_by(*args, **kwargs).all()
    select_by = classmethod(select_by)

    def selectfirst(cls, *args, **kwargs):
        warnings.warn("The selectfirst method on the class is deprecated."
                      "You should use cls.query.filter(...).first()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter(*args, **kwargs).first()
    selectfirst = classmethod(selectfirst)

    def selectfirst_by(cls, *args, **kwargs):
        warnings.warn("The selectfirst_by method on the class is deprecated."
                      "You should use cls.query.filter_by(...).first()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter_by(*args, **kwargs).first()
    selectfirst_by = classmethod(selectfirst_by)

    def selectone(cls, *args, **kwargs):
        warnings.warn("The selectone method on the class is deprecated."
                      "You should use cls.query.filter(...).one()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter(*args, **kwargs).one()
    selectone = classmethod(selectone)

    def selectone_by(cls, *args, **kwargs):
        warnings.warn("The selectone_by method on the class is deprecated."
                      "You should use cls.query.filter_by(...).one()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter_by(*args, **kwargs).one()
    selectone_by = classmethod(selectone_by)

    def join_to(cls, *args, **kwargs):
        warnings.warn("The join_to method on the class is deprecated."
                      "You should use cls.query.join(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.join_to(*args, **kwargs).all()
    join_to = classmethod(join_to)

    def join_via(cls, *args, **kwargs):
        warnings.warn("The join_via method on the class is deprecated."
                      "You should use cls.query.join(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.join_via(*args, **kwargs).all()
    join_via = classmethod(join_via)

    def count(cls, *args, **kwargs):
        warnings.warn("The count method on the class is deprecated."
                      "You should use cls.query.filter(...).count()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter(*args, **kwargs).count()
    count = classmethod(count)

    def count_by(cls, *args, **kwargs):
        warnings.warn("The count_by method on the class is deprecated."
                      "You should use cls.query.filter_by(...).count()", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.filter_by(*args, **kwargs).count()
    count_by = classmethod(count_by)

    def options(cls, *args, **kwargs):
        warnings.warn("The options method on the class is deprecated."
                      "You should use cls.query.options(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.options(*args, **kwargs)
    options = classmethod(options)

    def instances(cls, *args, **kwargs):
        warnings.warn("The instances method on the class is deprecated."
                      "You should use cls.query.instances(...)", 
                      DeprecationWarning, stacklevel=2)
        return cls.query.instances(*args, **kwargs)
    instances = classmethod(instances)



class Objectstore(object):
    """a wrapper for a SQLAlchemy session-making object, such as 
    SessionContext or ScopedSession.
    
    Uses the ``registry`` attribute present on both objects
    (versions 0.3 and 0.4) in order to return the current
    contextual session.
    """
    
    def __init__(self, ctx):
        self.context = ctx

    def __getattr__(self, name):
        return getattr(self.context.registry(), name)
    
    session = property(lambda s:s.context.registry())

