"""
test autoloaded entities
"""

from sqlalchemy import Table, Column, ForeignKey
from elixir import *
import elixir

def setup_entity_raise(cls):
    try:
        setup_entities([cls])
    except Exception, e:
        pass
    else:
        assert False, "Exception did not occur setting up %s" % cls.__name__

# ------

def setup():
    elixir.options_defaults.update(dict(autoload=True, shortnames=True))

def teardown():
    elixir.options_defaults.update(dict(autoload=False, shortnames=False))

# -----------

class TestAutoload(object):
    def setup(self):
        metadata.bind = 'sqlite://'

    def teardown(self):
        cleanup_all(True)

    def test_simple(self):
        #FIXME: use raw SQL or clear metadata between autoload table definition and autoload !!!!
        person_table = Table('person', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(32)))

        animal_table = Table('animal', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(30)),
            Column('owner_id', Integer, ForeignKey('person.id')),
            Column('feeder_id', Integer, ForeignKey('person.id')))

        metadata.create_all()
        metadata.clear()

        class Person(Entity):
            pets = OneToMany('Animal', inverse='owner')
            animals = OneToMany('Animal', inverse='feeder')

        class Animal(Entity):
            owner = ManyToOne('Person', colname='owner_id')
            feeder = ManyToOne('Person', colname='feeder_id')

        setup_all()

        snowball = Animal(name="Snowball II")
        slh = Animal(name="Santa's Little Helper")
        homer = Person(name="Homer", animals=[snowball, slh], pets=[slh])
        lisa = Person(name="Lisa", pets=[snowball])

        session.commit()
        session.clear()

        homer = Person.get_by(name="Homer")
        lisa = Person.get_by(name="Lisa")
        slh = Animal.get_by(name="Santa's Little Helper")

        assert len(homer.animals) == 2
        assert homer == lisa.pets[0].feeder
        assert homer == slh.owner

    def test_selfref(self):
        person_table = Table('person', metadata,
            Column('id', Integer, primary_key=True),
            Column('father_id', Integer, ForeignKey('person.id')),
            Column('name', String(32)))
        metadata.create_all()

        class Person(Entity):
            father = ManyToOne('Person')
            children = OneToMany('Person')

        setup_all()

        grampa = Person(name="Abe")
        homer = Person(name="Homer")
        bart = Person(name="Bart")
        lisa = Person(name="Lisa")

        grampa.children.append(homer)
        homer.children.append(bart)
        lisa.father = homer

        session.commit()
        session.clear()

        p = Person.get_by(name="Homer")

        assert p in p.father.children
        assert p.father.name == "Abe"
        assert p.father is Person.get_by(name="Abe")
        assert p is Person.get_by(name="Lisa").father

    def test_m2m(self):
        person_table = Table('person', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(32)))

        category_table = Table('category', metadata,
            Column('name', String(30), primary_key=True))

        person_category_table = Table('person_category', metadata,
            Column('person_id', Integer, ForeignKey('person.id')),
            Column('category_name', String(30), ForeignKey('category.name')))

        metadata.create_all()

        class Person(Entity):
            categories = ManyToMany('Category',
                                    tablename='person_category')

        class Category(Entity):
            persons = ManyToMany('Person',
                                 tablename='person_category')

        setup_all()

        stupid = Category(name="Stupid")
        simpson = Category(name="Simpson")
        old = Category(name="Old")

        grampa = Person(name="Abe", categories=[simpson, old])
        homer = Person(name="Homer", categories=[simpson, stupid])
        bart = Person(name="Bart")
        lisa = Person(name="Lisa")

        simpson.persons.extend([bart, lisa])

        session.commit()
        session.clear()

        c = Category.get_by(name="Simpson")
        grampa = Person.get_by(name="Abe")

        assert len(c.persons) == 4
        assert c in grampa.categories

    def test_m2m_selfref(self):
        person_table = Table('person', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(32)))

        person_person_table = Table('person_person', metadata,
            Column('person_id1', Integer, ForeignKey('person.id')),
            Column('person_id2', Integer, ForeignKey('person.id')))

        metadata.create_all()

        class Person(Entity):
            appreciate = ManyToMany('Person',
                                    tablename='person_person',
                                    local_colname='person_id1')
            isappreciatedby = ManyToMany('Person',
                                         tablename='person_person',
                                         local_colname='person_id2')

        setup_all()

        barney = Person(name="Barney")
        homer = Person(name="Homer", appreciate=[barney])

        session.commit()
        session.clear()

        homer = Person.get_by(name="Homer")
        barney = Person.get_by(name="Barney")

        assert barney in homer.appreciate
        assert homer in barney.isappreciatedby

    # ----------------
    # overrides tests
    # ----------------
    def _create_table_a(self):
        a_table = Table('a', metadata,
            Column('id', Integer, primary_key=True),
            Column('name', String(32)))

        metadata.create_all()

    def test_override_pk_fails(self):
        self._create_table_a()

        class A(Entity):
            id = Field(Integer, primary_key=True)

        setup_entity_raise(A)

    def test_override_non_pk_fails(self):
        self._create_table_a()

        class A(Entity):
            name = Field(String(30))

        setup_entity_raise(A)

    def test_override_pk(self):
        self._create_table_a()

        class A(Entity):
            using_options(allowcoloverride=True)

            id = Field(Integer, primary_key=True)

        setup_entities([A])

    def test_override_non_pk(self):
        self._create_table_a()

        class A(Entity):
            using_options(allowcoloverride=True)

            name = Field(String(30))

        setup_entities([A])
        assert isinstance(A.table.columns['name'].type, String)

    # ---------------

    def test_nopk(self):
        table = Table('a', metadata,
            Column('id', Integer),
            Column('name', String(32)))

        metadata.create_all()

        class A(Entity):
            using_mapper_options(primary_key=['id'])

        setup_all()

        a1 = A(id=1, name="a1")

        session.commit()
        session.clear()

        res = A.query.all()

        assert len(res) == 1
        assert res[0].name == "a1"

    def test_inheritance(self):
        table = Table('father', metadata,
            Column('id', Integer, primary_key=True),
            Column('row_type', elixir.options.POLYMORPHIC_COL_TYPE))

        metadata.create_all()

        class Father(Entity):
            pass

        class Son(Father):
            pass

        setup_all()
