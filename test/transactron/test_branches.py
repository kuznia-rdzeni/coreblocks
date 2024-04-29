from amaranth import *
from itertools import product
from transactron.core import (
    TModule,
    Method,
    Transaction,
    TransactionManager,
    TransactionModule,
    def_method,
)
from transactron.core.tmodule import CtrlPath
from transactron.core.manager import MethodMap
from unittest import TestCase
from transactron.testing import TestCaseWithSimulator
from transactron.utils.dependencies import DependencyContext


class TestExclusivePath(TestCase):
    def test_exclusive_path(self):
        m = TModule()
        m._MustUse__silence = True  # type: ignore

        with m.If(0):
            cp0 = m.ctrl_path
            with m.Switch(3):
                with m.Case(0):
                    cp0a0 = m.ctrl_path
                with m.Case(1):
                    cp0a1 = m.ctrl_path
                with m.Default():
                    cp0a2 = m.ctrl_path
            with m.If(1):
                cp0b0 = m.ctrl_path
            with m.Else():
                cp0b1 = m.ctrl_path
        with m.Elif(1):
            cp1 = m.ctrl_path
            with m.FSM():
                with m.State("start"):
                    cp10 = m.ctrl_path
                with m.State("next"):
                    cp11 = m.ctrl_path
        with m.Else():
            cp2 = m.ctrl_path

        def mutually_exclusive(*cps: CtrlPath):
            return all(cpa.exclusive_with(cpb) for i, cpa in enumerate(cps) for cpb in cps[i + 1 :])

        def pairwise_exclusive(cps1: list[CtrlPath], cps2: list[CtrlPath]):
            return all(cpa.exclusive_with(cpb) for cpa, cpb in product(cps1, cps2))

        def pairwise_not_exclusive(cps1: list[CtrlPath], cps2: list[CtrlPath]):
            return all(not cpa.exclusive_with(cpb) for cpa, cpb in product(cps1, cps2))

        assert mutually_exclusive(cp0, cp1, cp2)
        assert mutually_exclusive(cp0a0, cp0a1, cp0a2)
        assert mutually_exclusive(cp0b0, cp0b1)
        assert mutually_exclusive(cp10, cp11)
        assert pairwise_exclusive([cp0, cp0a0, cp0a1, cp0a2, cp0b0, cp0b1], [cp1, cp10, cp11])
        assert pairwise_not_exclusive([cp0, cp0a0, cp0a1, cp0a2], [cp0, cp0b0, cp0b1])


class ExclusiveConflictRemovalCircuit(Elaboratable):
    def __init__(self):
        self.sel = Signal()

    def elaborate(self, platform):
        m = TModule()

        called_method = Method(i=[], o=[])

        @def_method(m, called_method)
        def _():
            pass

        with m.If(self.sel):
            with Transaction().body(m):
                called_method(m)
        with m.Else():
            with Transaction().body(m):
                called_method(m)

        return m


class TestExclusiveConflictRemoval(TestCaseWithSimulator):
    def test_conflict_removal(self):
        circ = ExclusiveConflictRemovalCircuit()

        tm = TransactionManager()
        dut = TransactionModule(circ, DependencyContext.get(), tm)

        with self.run_simulation(dut, add_transaction_module=False):
            pass

        cgr, _ = tm._conflict_graph(MethodMap(tm.transactions))

        for s in cgr.values():
            assert not s
