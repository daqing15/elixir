'''
Elixir package

A declarative layer on top of SQLAlchemy, which is intended to replace the
ActiveMapper SQLAlchemy extension, and the TurboEntity project.  Elixir is a
fairly thin wrapper around SQLAlchemy, which provides the ability to define
model objects following the Active Record design pattern, and using a DSL
syntax similar to that of the Ruby on Rails ActiveRecord system.

Elixir does not intend to replace SQLAlchemy's core features, but instead
focuses on providing a simpler syntax for defining model objects when you do
not need the full expressiveness of SQLAlchemy's manual mapper definitions.

For an example of how to use Elixir, please refer to the examples directory
and the unit tests. The examples directory includes a TurboGears application
with full identity support called 'videostore'.
'''

import sqlalchemy

from sqlalchemy.ext.sessioncontext import SessionContext
from sqlalchemy.types import *

from elixir.options import using_options, using_table_options, \
                           using_mapper_options, options_defaults
from elixir.entity import Entity, EntityMeta, EntityDescriptor
from elixir.fields import has_field, with_fields, Field
from elixir.relationships import belongs_to, has_one, has_many, \
                                 has_and_belongs_to_many
from elixir.properties import has_property

try:
    set
except NameError:
    from sets import Set as set

__version__ = '0.3.0'

__all__ = ['Entity', 'EntityMeta', 'Field', 'has_field', 'with_fields',
           'has_property', 
           'belongs_to', 'has_one', 'has_many', 'has_and_belongs_to_many',
           'using_options', 'using_table_options', 'using_mapper_options',
           'options_defaults', 'metadata', 'objectstore',
           'create_all', 'drop_all', 'setup_all', 'cleanup_all',
           'delay_setup'] + \
          sqlalchemy.types.__all__

__pudge_all__ = ['create_all', 'drop_all', 'setup_all', 'cleanup_all',
                 'metadata', 'objectstore', 'delay_setup']

# connect
metadata = sqlalchemy.DynamicMetaData('elixir', threadlocal=False)

try:
    # this only happens when the threadlocal extension is used
    objectstore = sqlalchemy.objectstore
except AttributeError:
    # thread local SessionContext
    class Objectstore(object):

        def __init__(self, *args, **kwargs):
            self.context = SessionContext(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.context.current, name)
        session = property(lambda s:s.context.current)

    objectstore = Objectstore(sqlalchemy.create_session)

metadatas = set()


def create_all():
    'Create all necessary tables for all declared entities'
    for md in metadatas:
        md.create_all()


def drop_all():
    'Drop all tables for all declared entities'
    for md in metadatas:
        md.drop_all()

delayed_entities = set()
delay_setup = False


def setup_all():
    '''Setup the table and mapper for all entities which have been delayed.

    This should be used in conjunction with setting ``delay_setup`` to ``True``
    before defining your entities.
    '''
    for entity in delayed_entities:
        entity.setup_table()
    for entity in delayed_entities:
        entity.setup_mapper()

    # setup all relationships
    for entity in delayed_entities:
        for rel in entity.relationships.itervalues():
            rel.setup()

    delayed_entities.clear()

    # issue the "CREATE" SQL statements
    create_all()


def cleanup_all():
    '''Drop table and clear mapper for all entities, and clear all metadatas.
    '''
    drop_all()
    for md in metadatas:
        md.clear()
    metadatas.clear()
    EntityDescriptor.uninitialized_rels.clear()

    objectstore.clear()
    sqlalchemy.clear_mappers()

