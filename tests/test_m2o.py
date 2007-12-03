"""
test many to one relationships
"""

from elixir import *

def setup():
    metadata.bind = 'sqlite:///'

class TestManyToOne(object):
    def teardown(self):
        cleanup_all(True)
    
    def test_simple(self):
        class A(Entity):
            name = Field(String(60))

        class B(Entity):
            name = Field(String(60))
            a = ManyToOne('A')

        setup_all(True)

        b1 = B(name='b1', a=A(name='a1'))

        session.flush()
        session.clear()

        b = B.query.one()

        assert b.a.name == 'a1'

    def test_with_key_pk(self):
        class A(Entity):
            test = Field(Integer, primary_key=True, key='testx')

        class B(Entity):
            a = ManyToOne('A')
            
        setup_all(True)
        
        b1 = B(a=A(testx=1))
        
        session.flush()
        session.clear()
        
        b = B.query.one()

        assert b.a.testx == 1

    def test_one_pk(self):
        class A(Entity):
            name = Field(String(40), primary_key=True)
         
        class B(Entity):
            a = ManyToOne('A', primary_key=True)
         
        class C(Entity):
            b = ManyToOne('B', primary_key=True)

        setup_all()

        assert A.table.primary_key.columns.has_key('name')
        assert B.table.primary_key.columns.has_key('a_name')
        assert C.table.primary_key.columns.has_key('b_a_name')

    def test_m2o_is_only_pk(self):
        class A(Entity):
            pass
         
        class B(Entity):
            a = ManyToOne('A', primary_key=True)
         
        setup_all()

        assert A.table.primary_key.columns.has_key('id')
        assert B.table.primary_key.columns.has_key('a_id')
        assert not B.table.primary_key.columns.has_key('id')

    def test_multi_pk_in_target(self):
        class A(Entity):
            key1 = Field(Integer, primary_key=True)
            key2 = Field(String(40), primary_key=True)
         
        class B(Entity):
            num = Field(Integer, primary_key=True)
            a = ManyToOne('A', primary_key=True)
         
        class C(Entity):
            num = Field(Integer, primary_key=True)
            b = ManyToOne('B', primary_key=True)

        setup_all()

        assert A.table.primary_key.columns.has_key('key1')
        assert A.table.primary_key.columns.has_key('key2')

        assert B.table.primary_key.columns.has_key('num')
        assert B.table.primary_key.columns.has_key('a_key1')
        assert B.table.primary_key.columns.has_key('a_key2')

        assert C.table.primary_key.columns.has_key('num')
        assert C.table.primary_key.columns.has_key('b_num')
        assert C.table.primary_key.columns.has_key('b_a_key1')
        assert C.table.primary_key.columns.has_key('b_a_key2')

    def test_cycle_but_use_alter(self):
        class A(Entity):
            c = ManyToOne('C', use_alter=True)
         
        class B(Entity):
            a = ManyToOne('A', primary_key=True)
         
        class C(Entity):
            b = ManyToOne('B', primary_key=True)

        setup_all()

        assert B.table.primary_key.columns.has_key('a_id')
        assert C.table.primary_key.columns.has_key('b_a_id')
        assert A.table.primary_key.columns.has_key('id')
        assert A.table.columns.has_key('c_b_a_id')

    def test_multi(self):
        class A(Entity):
            name = Field(String(32))
            
        class B(Entity):
            name = Field(String(15))
            
            a_rel1 = ManyToOne('A')
            a_rel2 = ManyToOne('A')

        setup_all(True)

        a1 = A(name="a1")
        a2 = A(name="a2")
        b1 = B(name="b1", a_rel1=a1, a_rel2=a2)
        b2 = B(name="b2", a_rel1=a1, a_rel2=a1)
        
        session.flush()
        session.clear()
        
        a1 = A.get_by(name="a1")
        a2 = A.get_by(name="a2")
        b1 = B.get_by(name="b1")
        b2 = B.get_by(name="b2")
        
        assert a1 == b2.a_rel1
        assert a2 == b1.a_rel2

    def test_belongs_to_syntax(self):
        class Person(Entity):
            has_field('name', String(30))

        class Animal(Entity):
            has_field('name', String(30))
            belongs_to('owner', of_kind='Person')

        setup_all(True)
        
        santa = Person(name="Santa Claus")
        rudolph = Animal(name="Rudolph", owner=santa)
        
        session.flush()
        session.clear()
        
        assert "Claus" in Animal.get_by(name="Rudolph").owner.name
