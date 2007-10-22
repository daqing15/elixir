"""
test many to many relationships
"""

from elixir import *

#-----------

class TestManyToMany(object):
    def setup(self):
        metadata.bind = 'sqlite:///'
    
    def teardown(self):
        cleanup_all(True)
    
    def test_simple(self):
        class A(Entity):
            name = Field(Unicode(60))
            bs_ = ManyToMany('B')

        class B(Entity):
            name = Field(Unicode(60))
            as_ = ManyToMany('A')

        setup_all(True)

        b1 = B(name='b1', as_=[A(name='a1')])

        session.flush()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert a in b.as_
        assert b in a.bs_

    def test_multi(self):
        class A(Entity):
            name = Field(String(100))

            rel1 = ManyToMany('B')
            rel2 = ManyToMany('B')
            
        class B(Entity):
            name = Field(String(20), primary_key=True)

        setup_all(True)
        
        b1 = B(name='b1')
        a1 = A(name='a1', rel1=[B(name='b2'), b1],
                          rel2=[B(name='b3'), B(name='b4'), b1])

        session.flush()
        session.clear()
        
        a1 = A.query.one()
        b1 = B.get_by(name='b1')
        b2 = B.get_by(name='b2')

        assert b1 in a1.rel1 
        assert b1 in a1.rel2
        assert b2 in a1.rel1

    def test_selfref(self):
        class Person(Entity):
            name = Field(Unicode(30))
            
            friends = ManyToMany('Person')

        create_all()

        barney = Person(name="Barney")
        homer = Person(name="Homer", friends=[barney])
        barney.friends.append(homer)

        session.flush()
        session.clear()
        
        homer = Person.get_by(name="Homer")
        barney = Person.get_by(name="Barney")

        assert homer in barney.friends
        assert barney in homer.friends

    def test_has_and_belongs_to_many(self):
        class A(Entity):
            has_field('name', String(100))

            has_and_belongs_to_many('bs', of_kind='B')
            
        class B(Entity):
            has_field('name', String(100), primary_key=True)

        setup_all(True)
        
        b1 = B(name='b1')
        a1 = A(name='a1', bs=[B(name='b2'), b1])
        a2 = A(name='a2', bs=[B(name='b3'), b1])
        a3 = A(name='a3')

        session.flush()
        session.clear()
        
        a1 = A.get_by(name='a1')
        a2 = A.get_by(name='a2')
        a3 = A.get_by(name='a3')
        b1 = B.get_by(name='b1')
        b2 = B.get_by(name='b2')

        assert b1 in a1.bs
        assert b2 in a1.bs
        assert b1 in a2.bs
        assert not a3.bs

