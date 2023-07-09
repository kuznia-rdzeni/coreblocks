from amaranth import *

from enum import IntFlag, auto

from typing import Sequence

from transactron import *
from transactron.core import Priority
from transactron.lib import *

from coreblocks.params import *
from coreblocks.params.keys import MretKey
from coreblocks.utils.protocols import FuncUnit
from coreblocks.utils import assign, AssignType

from coreblocks.fu.fu_decoder import DecoderManager


class IntRetFn(DecoderManager):
    @unique
    class Fn(IntFlag):
        MRET = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [(cls.Fn.MRET, OpType.MRET)]


class IntRetFuncUnit(Elaboratable):
    def __init__(self, gen: GenParams, intret_fn=IntRetFn()):
        self.gen = gen

        self.layouts = layouts = gen.get(FuncUnitLayouts)
        self.connections = gen.get(DependencyManager)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.clear = Method()
        self.precommit = Method(i=layouts.precommit)

    def elaborate(self, platform):
        m = TModule()

        instr = Record(self.layouts.accept)
        pending_instr = Signal()
        finished = Signal()

        @def_method(m, self.accept, ready=pending_instr & finished)
        def _():
            m.d.sync += pending_instr.eq(0)
            return instr

        @def_method(m, self.issue, ready=~pending_instr)
        def _(arg):
            m.d.sync += assign(instr, arg, fields=AssignType.COMMON)
            m.d.sync += pending_instr.eq(1)
            m.d.sync += finished.eq(0)

        @def_method(m, self.clear)
        def _():
            m.d.sync += pending_instr.eq(0)

        mret_trigger = self.connections.get_dependency(MretKey())

        @def_method(m, self.precommit)
        def _(rob_id):
            with m.If(pending_instr & ~finished & (rob_id == instr.rob_id)):
                m.d.sync += finished.eq(1)
                mret_trigger(m)

        self.clear.add_conflict(self.issue, priority=Priority.LEFT)
        self.clear.add_conflict(self.accept, priority=Priority.LEFT)
        self.clear.add_conflict(self.precommit, priority=Priority.LEFT)

        return m


class IntRetComponent(FunctionalComponentParams):
    def __init__(self):
        self.fn = IntRetFn()

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = IntRetFuncUnit(gen_params, self.fn)
        connections = gen_params.get(DependencyManager)
        connections.add_dependency(InstructionPrecommitKey(), unit.precommit)
        return unit

    def get_optypes(self) -> set[OpType]:
        return self.fn.get_op_types()
