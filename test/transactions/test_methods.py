# amaranth: UnusedElaboratable=no

from amaranth import *
from amaranth.sim import *

from ..common import TestCaseWithSimulator

from coreblocks.transactions import *


class TestDefMethod(TestCaseWithSimulator):
    class TestModule(Elaboratable):
        def __init__(self, method_define_fn):
            self.transactionManager = TransactionManager()
            self.method = Method(
                o=[
                    ("foo1", 3),
                    ("foo2", [("bar1", 4), ("bar2", 6)]),
                ],
                manager=self.transactionManager,
            )

            self.method_define_fn = method_define_fn

        def elaborate(self, platform):
            m = Module()

            self.method_define_fn(m, self.method)

            m.submodules += self.transactionManager

            return m

    def do_test_definition(self, definer):
        with self.runSimulation(TestDefMethod.TestModule(definer)):
            pass

    def test_fields_valid1(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        self.do_test_definition(method_definer)

    def test_fields_valid2(self):
        def method_definer(m, method):
            rec = Record([("bar1", 4), ("bar2", 6)])

            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "foo2": rec}

        self.do_test_definition(method_definer)

    def test_fields_invalid1(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3), "baz": Signal(4)}

        with self.assertRaises(AttributeError):
            self.do_test_definition(method_definer)

    def test_fields_invalid2(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": Signal(3)}

        with self.assertRaises(KeyError):
            self.do_test_definition(method_definer)

    def test_fields_invalid3(self):
        def method_definer(m, method):
            @def_method(m, method)
            def _(arg):
                return {"foo1": {"baz1": Signal(), "baz2": Signal()}, "foo2": {"bar1": Signal(4), "bar2": Signal(6)}}

        with self.assertRaises(TypeError):
            self.do_test_definition(method_definer)
