"""
    simple test case
"""

from elixir import *
import sys

def setup(self):
    metadata.bind = 'sqlite:///'

class TestPackages(object):
    def teardown(self):
        cleanup_all(True)
    
    def test_packages(self):
        # This is an ugly workaround because when nosetest is run globally (ie
        # either on the tests directory or in the "trunk" directory, it imports
        # all modules, including a and b. Then when any other test calls
        # setup_all(), A and B are also setup, but then the other test also
        # calls cleanup_all(), so when we get here, A and B are already dead and
        # reimporting their modules does nothing because they were already
        # imported.
        sys.modules.pop('tests.a', None)
        sys.modules.pop('tests.b', None)

        from tests.a import A
        from tests.b import B

        setup_all(True)

        b1 = B(name='b1', as_=[A(name='a1')])

        session.flush()
        session.clear()

        a = A.query.one()

        assert a in a.b.as_

    def test_ref_to_imported_entity_using_class(self):
        sys.modules.pop('tests.a', None)
        sys.modules.pop('tests.b', None)

        from tests.a import A
        from tests.b import B

        class C(Entity):
            name = Field(String(30))
            a = ManyToOne(A)

        setup_all(True)

        # 'a_id' in ... is not supported before SA 0.4
        assert C.table.columns.has_key('a_id')

    def test_ref_to_imported_entity_using_name(self):
        sys.modules.pop('tests.a', None)
        sys.modules.pop('tests.b', None)

        from tests.a import A
        from tests.b import B

        class C(Entity):
            name = Field(String(30))
            a = ManyToOne('A')

        setup_all(True)

        assert C.table.columns.has_key('a_id')

