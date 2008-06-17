"""
    simple test case
"""

from sqlalchemy import Table
from elixir import *
import elixir


def setup():
    metadata.bind = 'sqlite:///'

def teardown():
    cleanup_all()

class TestSetup(object):
    def teardown(self):
        cleanup_all()
    
    def test_no_collection(self):
        class Person(Entity):
            name = Field(String(30))
            using_options(autosetup=False, tablename='person', collection=None)

        # global collection should be empty
        assert not elixir.entities

        setup_entities([Person])

        # check the table was correctly setup
        assert isinstance(metadata.tables['person'], Table)

    def test_several_collections(self):
        #FIXME: this test fails because the collections are simple lists and 
        # the code in entity.py:140 assumes the collection object has a 
        # map_entity method.
        collection1 = []
        collection2 = []

        class A(Entity):
            name = Field(String(30))
            using_options(collection=collection1, autosetup=False, 
                          tablename='a')

        class B(Entity):
            name = Field(String(30))
            using_options(collection=collection2, autosetup=False,
                          tablename='b')

        # global collection should be empty
        assert A not in elixir.entities
        assert B not in elixir.entities

        assert A in collection1
        assert B in collection2

        setup_entities(collection1)
        setup_entities(collection2)

        assert isinstance(metadata.tables['a'], Table)
        assert isinstance(metadata.tables['b'], Table)

    def test_setup_after_cleanup(self):
        class A(Entity):
            name = Field(String(30))
            using_options(autosetup=False, tablename='a')

        setup_all()

        assert isinstance(metadata.tables['a'], Table)

        cleanup_all()

        assert 'a' not in metadata.tables

        # setup_all wouldn't work since the entities list is now empty
        setup_entities([A])

        assert isinstance(metadata.tables['a'], Table)

        # cleanup manually
        cleanup_entities([A])

        # metadata is not in metadatas anymore (removed by cleanup_all) and not
        # added back by setup_entities (maybe we should?)
        metadata.clear()


