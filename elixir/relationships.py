from sqlalchemy         import relation, ForeignKeyConstraint, Column, \
                               Table, and_
from elixir.statements  import Statement
from elixir.fields      import Field
from elixir.entity      import EntityDescriptor

import sys


__all__ = [
    'belongs_to',
    'has_one',
    'has_many',
    'has_and_belongs_to_many'
]


class Relationship(object):
    '''
    Base class for relationships
    '''
    
    def __init__(self, entity, name, *args, **kwargs):
        self.name = name
        self.of_kind = kwargs.pop('of_kind')
        self.inverse_name = kwargs.pop('inverse', None)
        
        self.entity = entity
        self._target = None
        
        self.initialized = False
        self.secondary = None
        self._inverse = None
        self.foreign_key = None
        
        self.foreign_key = kwargs.pop('foreign_key', None)
        if self.foreign_key and not isinstance(self.foreign_key, list):
            self.foreign_key = [self.foreign_key]
        
        self.property = None # sqlalchemy property
        
        self.args = args
        self.kwargs = kwargs
        
        #CHECKME: is this useful?
        self.entity._descriptor.relationships[self.name] = self
    
    def create_keys(self):
        '''
        Subclasses (ie. concrete relationships) may override this method to 
        create foreign keys.
        '''
    
    def create_tables(self):
        '''
        Subclasses (ie. concrete relationships) may override this method to 
        create secondary tables.
        '''
    
    def create_properties(self):
        '''
        Subclasses (ie. concrete relationships) may override this method to add 
        properties to the involved entities.
        '''
    
    def setup(self):
        '''
        Sets up the relationship, creates foreign keys and secondary tables.
        '''
        
        if not self.target:
            return False
        
        self.create_keys()
        self.create_tables()
        self.create_properties()
        
        return True
    
    @property
    def target(self):
        if not self._target:
            path = self.of_kind.rsplit('.', 1)
            classname = path.pop()

            # full qualified entity name?
            if path:
                module = sys.modules[path.pop()]
            # if not, try the same module as the source
            else: 
                module = self.entity._descriptor.module
            
            try:
                self._target = getattr(module, classname)
            except AttributeError:
                # TODO: don't use exceptions for logic here!
                # This is ugly but we need it because the class which is
                # currently being defined (we have to keep in mind we are in 
                # its metaclass code) is not yet available in the module
                # namespace, so the getattr above fails. And unfortunately,
                # this doesn't only happen for the owning entity of this
                # relation since we might be setting up a deferred relation.
                e = EntityDescriptor.current.entity
                if classname == e.__name__ or \
                        self.of_kind == e.__module__ +'.'+ e.__name__:
                    self._target = e
                else:
                    return None
        
        return self._target
    
    @property
    def inverse(self):
        #TODO: we should use a different value for when an inverse was searched
        # for but none was found than when it hasn't been searched for yet so
        # that we don't do the whole search again
        if not self._inverse:
            if self.inverse_name:
                desc = self.target._descriptor
                inverse = desc.relationships[self.inverse_name]
                assert self.match_type_of(inverse)
            else:
                inverse = self.target._descriptor.get_inverse_relation(self)
        
            if inverse:
                self._inverse = inverse
                inverse._inverse = self
        
        return self._inverse
    
    def match_type_of(self, other):
        t1, t2 = type(self), type(other)
    
        if t1 is HasAndBelongsToMany:
            return t1 is t2
        elif t1 in (HasOne, HasMany):
            return t2 is BelongsTo
        elif t1 is BelongsTo:
            return t2 in (HasMany, HasOne)
        else:
            return False

    def is_inverse(self, other):
        return other is not self and \
               self.match_type_of(other) and \
               self.entity == other.target and \
               other.entity == self.target and \
               (self.inverse_name == other.name or not self.inverse_name) and \
               (other.inverse_name == self.name or not other.inverse_name)


class BelongsTo(Relationship):
    
    def create_keys(self):
        '''
        Find all primary keys on the target and create foreign keys on the 
        source accordingly.
        '''
        
        source_desc = self.entity._descriptor
        target_desc = self.target._descriptor
        
        if self.foreign_key:
            self.foreign_key = [source_desc.fields[k]
                                    for k in self.foreign_key 
                                        if isinstance(k, basestring)]
            return
        
        fk_refcols = list()
        fk_colnames = list()

        self.foreign_key = list()
        self.primaryjoin_clauses = list()

        for key in target_desc.primary_keys:
            pk_col = key.column

            colname = '%s_%s' % (self.name, pk_col.name)
            # we use a Field here instead of using a Column directly 
            # because of add_field 
            field = Field(pk_col.type, colname=colname, index=True)
            source_desc.add_field(field)

            self.foreign_key.append(field)

            # build the list of local columns which will be part of
            # the foreign key
            fk_colnames.append(colname)

            # build the list of columns the foreign key will point to
            fk_refcols.append(target_desc.tablename + '.' + pk_col.name)

            # build up the primary join. This is needed when you have several
            # belongs_to relations between two objects
            self.primaryjoin_clauses.append(field.column == pk_col)
        
        # TODO: better constraint-naming?
        #CHECKME: do we really need use_alter systematically?
        source_desc.add_constraint(ForeignKeyConstraint(
                                        fk_colnames, fk_refcols,
                                        name=self.name +'_fk',
                                        use_alter=True))
    
    def create_properties(self):
        kwargs = self.kwargs
        
        if self.entity is self.target:
            cols = [k.column for k in self.target._descriptor.primary_keys]
            kwargs['remote_side'] = cols

        kwargs['primaryjoin'] = and_(*self.primaryjoin_clauses)
        kwargs['uselist'] = False
        
        self.property = relation(self.target, **kwargs)
        self.entity.mapper.add_property(self.name, self.property)


class HasOne(Relationship):
    uselist = False

    def create_keys(self):
        # make sure the inverse is set up because it creates the
        # foreign key we'll need
        self.inverse.setup()
    
    def create_properties(self):
        kwargs = self.kwargs
        
        if self.entity is self.target:
            kwargs['remote_side'] = [field.column
                                        for field in self.inverse.foreign_key]
        
        kwargs['primaryjoin'] = and_(*self.inverse.primaryjoin_clauses)
        kwargs['uselist'] = self.uselist
        
        self.property = relation(self.target, **kwargs)
        self.entity.mapper.add_property(self.name, self.property)


class HasMany(HasOne):
    uselist = True


class HasAndBelongsToMany(Relationship):
    
    def __init__(self, entity, name, *args, **kwargs):
        self.tablename = kwargs.pop('tablename', None)
        super(HasAndBelongsToMany, self).__init__(entity, name, *args, **kwargs)
    
    def create_tables(self):
        if self.inverse:
            if self.inverse.secondary:
                self.secondary = self.inverse.secondary
                self.primaryjoin_clauses = self.inverse.secondaryjoin_clauses
                self.secondaryjoin_clauses = self.inverse.primaryjoin_clauses

        if not self.secondary:
            e1_desc = self.entity._descriptor
            e2_desc = self.target._descriptor
            
            columns = list()
            constraints = list()

            self.primaryjoin_clauses = list()
            self.secondaryjoin_clauses = list()

            for num, desc, join_name in (('1', e1_desc, 'primary'), 
                                         ('2', e2_desc, 'secondary')):
                fk_colnames = list()
                fk_refcols = list()
            
                for key in desc.primary_keys:
                    pk_col = key.column
                    
                    colname = '%s_%s' % (desc.tablename, pk_col.name)

                    # In case we have a many-to-many self-reference, we need
                    # to tweak the names of the columns so that we don't end 
                    # up with twice the same column name.
                    if self.entity is self.target:
                        colname += num

                    col = Column(colname, pk_col.type)
                    columns.append(col)

                    # build the list of local columns which will be part of
                    # the foreign key
                    fk_colnames.append(colname)

                    # build the list of columns the foreign key will point to
                    fk_refcols.append(desc.tablename + '.' + pk_col.name)

                    # build join clauses
                    join_list = getattr(self, join_name+'join_clauses')
                    join_list.append(col == pk_col)
                
                # TODO: better constraint-naming?
                #CHECKME: do we really need use_alter systematically?
                constraints.append(
                    ForeignKeyConstraint(fk_colnames, fk_refcols,
                                         name=desc.tablename + '_fk', 
                                         use_alter=True))
        
            # In the table name code below, we use the name of the relation
            # for the first entity (instead of the name of its primary key), 
            # so that we can have two many-to-many relations between the same
            # objects without having a table name collision. On the other hand,
            # we use the name of the primary key for the second entity 
            # (instead of the inverse relation's name) so that a many-to-many
            # relation can be defined without inverse.
            if not self.tablename:
                e2_pk_name = '_'.join([key.column.name for key in
                                       e2_desc.primary_keys])
                tablename = "%s_%s__%s_%s" % (e1_desc.tablename, self.name,
                                              e2_desc.tablename, e2_pk_name)
            else:
                tablename = self.tablename

            args = columns + constraints
            self.secondary = Table(tablename, e1_desc.metadata, *args)
    
    def create_properties(self):
        kwargs = self.kwargs

        if self.target is self.entity:
            kwargs['primaryjoin'] = and_(*self.primaryjoin_clauses)
            kwargs['secondaryjoin'] = and_(*self.secondaryjoin_clauses)

        m = self.entity.mapper
        #FIXME: using post_update systematically is *really* not good
        m.add_property(self.name,
                       relation(self.target, secondary=self.secondary,
                                uselist=True, **kwargs))


belongs_to              = Statement(BelongsTo)
has_one                 = Statement(HasOne)
has_many                = Statement(HasMany)
has_and_belongs_to_many = Statement(HasAndBelongsToMany)
