'''
Elixir
    
A declarative layer on top of SQLAlchemy, which is intended to replace the
ActiveMapper SQLAlchemy extension, and the TurboEntity project.  Elixir is a
fairly thin wrapper around SQLAlchemy, which provides the ability to define 
model objects following the Active Record design pattern, and using a DSL 
syntax similar to that of the Ruby on Rails ActiveRecord system.

Elixir does not intend to replace SQLAlchemy's core features, but instead 
focuses on providing a simpler syntax for defining model objects when you do
not need the full expressiveness of SQLAlchemy's manual mapper definitions.

For an example of how to use Elixir, please refer to the examples directory and
the unit tests.  The examples directory includes a TurboGears application with
full identity support called 'videostore'.
'''

import sqlalchemy

from sqlalchemy.ext.sessioncontext  import SessionContext
from sqlalchemy.types               import *
from elixir.options                 import *
from elixir.entity                  import Entity, EntityDescriptor
from elixir.fields                  import Field, has_field, with_fields
from elixir.relationships           import belongs_to, has_one, has_many, \
                                           has_and_belongs_to_many

__all__ = ['Entity', 'Field', 'has_field', 'with_fields', 
           'belongs_to', 'has_one', 'has_many', 'has_and_belongs_to_many', 
           'using_options', 'using_table_options', 'using_mapper_options',
           'create_all', 'drop_all', 'metadata', 'objectstore'] + \
          sqlalchemy.types.__all__

# connect
metadata = sqlalchemy.DynamicMetaData('elixir')

try:
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
    """Create all necessary tables for all declared entities"""
    for md in metadatas:
        md.create_all()

def drop_all():
    """Drop all tables for all declared entities"""
    for md in metadatas:
        md.drop_all()
