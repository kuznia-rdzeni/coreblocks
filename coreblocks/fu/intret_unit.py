from amaranth import *

from enum import IntFlag, auto

from typing import Sequence

from coreblocks.transactions import *
from coreblocks.transactions.core import def_method
from coreblocks.transactions.lib import *

from coreblocks.params import *
from coreblocks.params.keys import MretKey
from coreblocks.utils import OneHotSwitch
from coreblocks.utils.protocols import FuncUnit
from coreblocks.utils.fifo import BasicFifo

from coreblocks.fu.fu_decoder import DecoderManager

class IntRetFn(DecoderManager):
    @unique
    class Fn(IntFlag):
       MRET = auto()

    @classmethod
    def get_instructions(cls) -> Sequence[tuple]:
        return [
            (cls.Fn.MRET, OpType.MRET)
        ]

class IntRetFuncUnit(Elaboratable):
    optypes = IntRetFn.get_op_types()

    def __init__(self, gen: GenParams):
        self.gen = gen

        layouts = gen.get(FuncUnitLayouts)
        self.connections = gen.get(DependencyManager)

        self.issue = Method(i=layouts.issue)
        self.accept = Method(o=layouts.accept)
        self.clear = Method()
        self.commit = Method(i=layouts.commit)

    def elaborate(self, platform):
        m = Module()

        m.submodules.fifo_mret = fifo_mret = BasicFifo(self.gen.get(FuncUnitLayouts).accept, 2)

        self.accept.proxy(m, fifo_mret.read)
        self.clear.proxy(m, fifo_mret.clear)

        @def_method(m, self.issue)
        def _(arg):
            fifo_mret.write(m, rob_id=arg.rob_id, result=0, rp_dst=arg.rp_dst)

        mret_trigger = self.connections.get_dependency(MretKey())

        # print(mret_trigger)
        @def_method(m, self.commit)
        def _(rob_id):
            mret_trigger(m)

        return m


class IntRetComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        unit = IntRetFuncUnit(gen_params)
        connections = gen_params.get(DependencyManager)
        connections.add_dependency(InstructionCommitKey(), unit.commit)
        return unit

    def get_optypes(self) -> set[OpType]:
        return IntRetFuncUnit.optypes