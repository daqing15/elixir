'''
A versioning plugin for Elixir.

Entities that are marked as versioned with the `acts_as_versioned` statement 
will automatically have a history table created and a timestamp and version
column added to their tables. In addition, versioned entities are provided 
with four new methods: revert, revert_to, compare_with and get_as_of, and one 
new attribute: versions.  Entities with compound primary keys are supported.

The `versions` attribute will contain a list of previous versions of the
instance, in increasing version number order.

The `get_as_of` method will retrieve a previous version of the instance "as of"
a specified datetime. If the current version is the most recent, it will be
returned.

The `revert` method will rollback the current instance to its previous version,
if possible. Once reverted, the current instance will be expired from the
session, and you will need to fetch it again to retrieve the now reverted
instance.

The `revert_to` method will rollback the current instance to the specified
version number, if possibe. Once reverted, the current instance will be expired
from the session, and you will need to fetch it again to retrieve the now
reverted instance.

The `compare_with` method will compare the instance with a previous version. A
dictionary will be returned with each field difference as an element in the
dictionary where the key is the field name and the value is a tuple of the
format (current_value, version_value). Version instances also have a
`compare_with` method so that two versions can be compared.

Also included in the module is a `after_revert` decorator that can be used to
decorate methods on the versioned entity that will be called following that 
instance being reverted.

The acts_as_versioned statement also accepts an optional `ignore` argument 
that consists of a list of strings, specifying names of fields.  Changes in 
those fields will not result in a version increment.

Note that relationships that are stored in mapping tables will not be included
as part of the versioning process, and will need to be handled manually. Only
values within the entity's main table will be versioned into the history table.
'''

from elixir                import Integer, DateTime
from elixir.statements     import Statement
from sqlalchemy            import Table, Column, and_, desc
from sqlalchemy.orm        import mapper, MapperExtension, EXT_PASS, \
                                  object_session
from datetime              import datetime

import inspect


#
# utility functions
#

def get_entity_where(instance):
    clauses = []
    for column in instance.table.primary_key.columns:
        instance_value = getattr(instance, column.name)
        clauses.append(column==instance_value)
    return and_(*clauses)


def get_history_where(instance):
    clauses = []
    for column in instance.table.primary_key.columns:
        instance_value = getattr(instance, column.name)
        history_column = getattr(instance.__history_table__.primary_key.columns, column.name)
        clauses.append(history_column==instance_value)
    return and_(*clauses)


#
# a mapper extension to track versions on insert, update, and delete
#

class VersionedMapperExtension(MapperExtension):
    def before_insert(self, mapper, connection, instance):
        instance.version = 1
        instance.timestamp = datetime.now()
        return EXT_PASS
        
    def after_insert(self, mapper, connection, instance):
        colvalues = dict([(key, getattr(instance, key)) for key in instance.c.keys()])
        instance.__class__.__history_table__.insert().execute(colvalues)
        return EXT_PASS
    
    def before_update(self, mapper, connection, instance):
        colvalues = dict([(key, getattr(instance, key)) for key in instance.c.keys()])
        history = instance.__class__.__history_table__
        
        values = history.select(get_history_where(instance), 
                                order_by=[desc(history.c.timestamp)],
                                limit=1).execute().fetchone()
        # In case the data was dumped into the db, the initial version might 
        # be missing so we put this version in as the original.
        if not values:
            instance.version = colvalues['version'] = 1
            instance.timestamp = colvalues['timestamp'] = datetime.now()
            history.insert().execute(colvalues)
            return EXT_PASS
        
        # SA might've flagged this for an update even though it didn't change.
        # This occurs when a relation is updated, thus marking this instance
        # for a save/update operation. We check here against the last version
        # to ensure we really should save this version and update the version
        # data.
        ignored = instance.__class__.__ignored_fields__
        for key in instance.c.keys():
            if key in ignored:
                continue
            if getattr(instance, key) != values[key]:
                # the instance was really updated, so we create a new version
                instance.version = colvalues['version'] = instance.version + 1
                instance.timestamp = colvalues['timestamp'] = datetime.now()
                history.insert().execute(colvalues)
                break

        return EXT_PASS
        
    def before_delete(self, mapper, connection, instance):
        instance.__history_table__.delete(
            get_history_where(instance)
        ).execute()
        return EXT_PASS


versioned_mapper_extension = VersionedMapperExtension()


#
# the acts_as_versioned statement
#

class VersionedEntityBuilder(object):
        
    def __init__(self, entity, ignore=[]):
        entity._descriptor.add_mapper_extension(versioned_mapper_extension)
        self.entity = entity
        # Changes in these fields will be ignored
        entity.__ignored_fields__ = ignore
        entity.__ignored_fields__.extend(['version', 'timestamp'])
        
    def create_non_pk_cols(self):
        # add a version column to the entity, along with a timestamp
        version_col = Column('version', Integer)
        timestamp_col = Column('timestamp', DateTime)
        self.entity._descriptor.add_column(version_col)
        self.entity._descriptor.add_column(timestamp_col)
   
    # we copy columns from the main entity table, so we need it to exist first
    def after_table(self):
        entity = self.entity

        # look for events
        after_revert_events = []
        for name, func in inspect.getmembers(entity, inspect.ismethod):
            if getattr(func, '_elixir_after_revert', False):
                after_revert_events.append(func)
        
        # create a history table for the entity
        #TODO: fail more noticeably in case there is a version col
        columns = [column.copy() for column in entity.table.c 
                                 if column.name != 'version']
        columns.append(Column('version', Integer, primary_key=True))
        table = Table(entity.table.name + '_history', entity.table.metadata, 
            *columns
        )
        entity.__history_table__ = table
        
        # create an object that represents a version of this entity
        class Version(object):
            pass
            
        # map the version class to the history table for this entity
        Version.__name__ = entity.__name__ + 'Version'
        Version.__versioned_entity__ = entity
        mapper(Version, entity.__history_table__)
                        
        # attach utility methods and properties to the entity
        def get_versions(self):
            return object_session(self).query(Version).filter(get_history_where(self)).all()
        
        def get_as_of(self, dt):
            # if the passed in timestamp is older than our current version's
            # time stamp, then the most recent version is our current version
            if self.timestamp < dt:
                return self
            
            # otherwise, we need to look to the history table to get our
            # older version
            query = object_session(self).query(Version)
            query = query.filter(and_(get_history_where(self), 
                                      Version.c.timestamp <= dt))
            query = query.order_by(desc(Version.c.timestamp)).limit(1)
            return query.first()
        
        def revert_to(self, to_version):
            hist = entity.__history_table__
            old_version = hist.select(and_(
                get_history_where(self), 
                hist.c.version == to_version
            )).execute().fetchone()
            
            entity.table.update(get_entity_where(self)).execute(
                dict(old_version.items())
            )
            
            hist.delete(and_(get_history_where(self), 
                             hist.c.version >= to_version)).execute()
            for event in after_revert_events: 
                event(self)
        
        def revert(self):
            assert self.version > 1
            self.revert_to(self.version - 1)
            
        def compare_with(self, version):
            differences = {}
            for column in self.c:
                if column.name == 'version':
                    continue
                this = getattr(self, column.name)
                that = getattr(version, column.name)
                if this != that:
                    differences[column.name] = (this, that)
            return differences
        
        entity.versions      = property(get_versions)
        entity.get_as_of     = get_as_of
        entity.revert_to     = revert_to
        entity.revert        = revert
        entity.compare_with  = compare_with
        Version.compare_with = compare_with

#def acts_as_versioned_handler(entity, ignore=[]):
#    builder = VersionedEntityBuilder(entity, ignore)
#    entity._descriptor.builders.append(builder)

#acts_as_versioned = ClassMutator(acts_as_versioned_handler)
acts_as_versioned = Statement(VersionedEntityBuilder)


#
# decorator for watching for revert events
#

def after_revert(func):
    func._elixir_after_revert = True
    return func


__all__ = ['acts_as_versioned', 'after_revert']
