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
            name = Field(String(60))
            bs_ = ManyToMany('B')

        class B(Entity):
            name = Field(String(60))
            as_ = ManyToMany('A')

        setup_all(True)

        b1 = B(name='b1', as_=[A(name='a1')])

        session.commit()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert a in b.as_
        assert b in a.bs_

    def test_column_format(self):
        class A(Entity):
            using_options(tablename='aye')
            name = Field(String(60))
            bs_ = ManyToMany('B', column_format='%(entity)s_%(key)s')

        class B(Entity):
            using_options(tablename='bee')
            name = Field(String(60))
            as_ = ManyToMany('A', column_format='%(entity)s_%(key)s')

        setup_all(True)

        b1 = B(name='b1', as_=[A(name='a1')])

        session.commit()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert a in b.as_
        assert b in a.bs_

        m2m_cols = A.bs_.property.secondary.columns
        assert 'a_id' in m2m_cols
        assert 'b_id' in m2m_cols

    def test_multi_pk_in_target(self):
        class A(Entity):
            key1 = Field(Integer, primary_key=True, autoincrement=False)
            key2 = Field(String(40), primary_key=True)

            bs_ = ManyToMany('B')

        class B(Entity):
            name = Field(String(60))
            as_ = ManyToMany('A')

        setup_all(True)

        b1 = B(name='b1', as_=[A(key1=10, key2='a1')])

        session.commit()
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

        session.commit()
        session.clear()

        a1 = A.query.one()
        b1 = B.get_by(name='b1')
        b2 = B.get_by(name='b2')

        assert b1 in a1.rel1
        assert b1 in a1.rel2
        assert b2 in a1.rel1

    def test_selfref(self):
        class Person(Entity):
            using_options(shortnames=True)
            name = Field(String(30))

            friends = ManyToMany('Person')

        setup_all(True)

        barney = Person(name="Barney")
        homer = Person(name="Homer", friends=[barney])
        barney.friends.append(homer)

        session.commit()
        session.clear()

        homer = Person.get_by(name="Homer")
        barney = Person.get_by(name="Barney")

        assert homer in barney.friends
        assert barney in homer.friends

    def test_bidirectional_selfref(self):
        class Person(Entity):
            using_options(shortnames=True)
            name = Field(String(30))

            friends = ManyToMany('Person')
            is_friend_of = ManyToMany('Person')

        setup_all(True)

        barney = Person(name="Barney")
        homer = Person(name="Homer", friends=[barney])
        barney.friends.append(homer)

        session.commit()
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

        session.commit()
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

    def test_local_and_remote_colnames(self):
        class A(Entity):
            using_options(shortnames=True)
            key1 = Field(Integer, primary_key=True, autoincrement=False)
            key2 = Field(String(40), primary_key=True)

            bs_ = ManyToMany('B', local_colname=['foo', 'bar'],
                                  remote_colname="baz")

        class B(Entity):
            using_options(shortnames=True)
            name = Field(String(60))
            as_ = ManyToMany('A', remote_colname=['foo', 'bar'],
                                  local_colname="baz")

        setup_all(True)

        b1 = B(name='b1', as_=[A(key1=10, key2='a1')])

        session.commit()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert a in b.as_
        assert b in a.bs_

    def test_manual_table_auto_joins(self):
        from sqlalchemy import Table, Column, ForeignKey, ForeignKeyConstraint

        a_b = Table('a_b', metadata,
                    Column('a_key1', None),
                    Column('a_key2', None),
                    Column('b_id', None, ForeignKey('b.id')),
                    ForeignKeyConstraint(['a_key1', 'a_key2'],
                                         ['a.key1', 'a.key2']))

        class A(Entity):
            using_options(shortnames=True)
            key1 = Field(Integer, primary_key=True, autoincrement=False)
            key2 = Field(String(40), primary_key=True)

            bs_ = ManyToMany('B', table=a_b)

        class B(Entity):
            using_options(shortnames=True)
            name = Field(String(60))
            as_ = ManyToMany('A', table=a_b)

        setup_all(True)

        b1 = B(name='b1', as_=[A(key1=10, key2='a1')])

        session.commit()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert a in b.as_
        assert b in a.bs_

    def test_manual_table_manual_joins(self):
        from sqlalchemy import Table, Column, ForeignKey, \
                               ForeignKeyConstraint, and_

        a_b = Table('a_b', metadata,
                    Column('a_key1', Integer),
                    Column('a_key2', String(40)),
                    Column('b_id', String(60)))

        class A(Entity):
            using_options(shortnames=True)
            key1 = Field(Integer, primary_key=True, autoincrement=False)
            key2 = Field(String(40), primary_key=True)

            bs_ = ManyToMany('B', table=a_b,
                             primaryjoin=lambda: and_(A.key1 == a_b.c.a_key1,
                                                      A.key2 == a_b.c.a_key2),
                             secondaryjoin=lambda: B.id == a_b.c.b_id,
                             foreign_keys=[a_b.c.a_key1, a_b.c.a_key2,
                                 a_b.c.b_id])

        class B(Entity):
            using_options(shortnames=True)
            name = Field(String(60))

        setup_all(True)

        a1 = A(key1=10, key2='a1', bs_=[B(name='b1')])

        session.commit()
        session.clear()

        a = A.query.one()
        b = B.query.one()

        assert b in a.bs_
