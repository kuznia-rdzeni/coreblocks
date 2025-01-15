from amaranth import *

from dataclasses import dataclass

from transactron.core import Priority, TModule, Method, Transaction, def_method
from transactron.lib import BasicFifo
from transactron.lib.connectors import Forwarder
from transactron.lib.simultaneous import condition
from transactron.utils import assign, layout_subset, AssignType

from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUComponent
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.params import GenParams, FunctionalComponentParams


class LSUAtomicWrapper(FuncUnit, Elaboratable):
    def __init__(self, gen_params: GenParams, lsu: FuncUnit):
        self.gen_params = gen_params
        self.lsu = lsu

        self.fu_layouts = fu_layouts = gen_params.get(FuncUnitLayouts)
        self.issue = Method(i=fu_layouts.issue)
        self.accept = Method(o=fu_layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        atomic_in_progress = Signal()
        atomic_op = Signal(
            layout_subset(self.fu_layouts.issue, fields=set(["rob_id", "s1_val", "s2_val", "rp_dst", "exec_fn"]))
        )

        def atomic_op_res(v1: Value, v2: Value):
            ret = Signal(self.gen_params.isa.xlen)

            cmp = Signal()
            ucmp = Signal()
            m.d.av_comb += cmp.eq(v1.as_signed() < v2.as_signed())
            m.d.av_comb += ucmp.eq(v1.as_unsigned() < v2.as_unsigned())

            funct7 = atomic_op.exec_fn.funct7
            rl = funct7[0]  # noqa: F841
            aq = funct7[1]  # noqa: F841

            with m.Switch(funct7 & ~0b11):
                with m.Case(Funct7.AMOSWAP):
                    m.d.av_comb += ret.eq(v2)
                with m.Case(Funct7.AMOADD):
                    m.d.av_comb += ret.eq(v1 + v2)
                with m.Case(Funct7.AMOXOR):
                    m.d.av_comb += ret.eq(v1 ^ v2)
                with m.Case(Funct7.AMOAND):
                    m.d.av_comb += ret.eq(v1 & v2)
                with m.Case(Funct7.AMOOR):
                    m.d.av_comb += ret.eq(v1 | v2)
                with m.Case(Funct7.AMOMIN):
                    m.d.av_comb += ret.eq(Mux(cmp, v1, v2))
                with m.Case(Funct7.AMOMAX):
                    m.d.av_comb += ret.eq(Mux(cmp, v2, v1))
                with m.Case(Funct7.AMOMINU):
                    m.d.av_comb += ret.eq(Mux(ucmp, v1, v2))
                with m.Case(Funct7.AMOMAXU):
                    m.d.av_comb += ret.eq(Mux(ucmp, v2, v1))

            return ret

        load_val = Signal(self.gen_params.isa.xlen)

        accept_forwarder = Forwarder(self.fu_layouts.accept)

        @def_method(m, self.issue, ready=~atomic_in_progress)
        def _(arg):
            is_atomic = arg.exec_fn.op_type == OpType.ATOMIC_MEMORY_OP

            atomic_load_op = Signal(self.fu_layouts.issue)
            m.d.av_comb += assign(atomic_load_op, arg)
            m.d.av_comb += assign(atomic_load_op.exec_fn, {"op_type": OpType.LOAD, "funct3": Funct3.W})
            m.d.av_comb += atomic_load_op.imm.eq(0)

            with m.If(is_atomic):
                self.lsu.issue(m, atomic_load_op)
            with m.Else():
                self.lsu.issue(m, arg)

            with m.If(is_atomic):
                m.d.sync += atomic_in_progress.eq(1)
                m.d.sync += assign(atomic_op, arg, fields=AssignType.LHS)

        @def_method(m, self.accept)
        def _():
            return accept_forwarder.read(m)

        atomic_second_reqest = Signal()
        atomic_fin = Signal()

        # NOTE: Accepting result from LSU is split to two transactions, to avoid combinational loop on rob_id condition.
        # Standard LSU path writes directly to forwarder with no delay, while atomic path is decoulpled from FU accept
        # readiness by FIFO.

        with Transaction().body(m, request=~atomic_in_progress) as lsu_forward_transaction:
            res = self.lsu.accept(m)
            accept_forwarder.write(m, res)

        atomic_res_fifo = BasicFifo(self.fu_layouts.accept, 2)

        with Transaction().body(m, request=atomic_in_progress):
            res = self.lsu.accept(m)

            with condition(m) as cond:
                # Remaining non-atomic results
                with cond(res.rob_id != atomic_op.rob_id):
                    atomic_res_fifo.write(m, res)

                # 1st atomic result
                with cond((res.rob_id == atomic_op.rob_id) & ~atomic_second_reqest & res.exception):
                    atomic_res_fifo.write(m, res)
                    m.d.sync += atomic_in_progress.eq(0)
                with cond((res.rob_id == atomic_op.rob_id) & ~atomic_second_reqest & ~res.exception):
                    m.d.sync += load_val.eq(res.result)
                    m.d.sync += atomic_second_reqest.eq(1)

                # 2nd atomic result
                with cond(atomic_fin):
                    atomic_res = Signal(self.fu_layouts.accept)
                    m.d.av_comb += assign(atomic_res, res)
                    m.d.av_comb += atomic_res.result.eq(Mux(res.exception, 0, load_val))
                    atomic_res_fifo.write(m, atomic_res)

                    m.d.sync += atomic_in_progress.eq(0)
                    m.d.sync += atomic_second_reqest.eq(0)
                    m.d.sync += atomic_fin.eq(0)

        with Transaction().body(m) as accept_atomic_transaction:
            accept_forwarder.write(m, atomic_res_fifo.read(m))
        accept_atomic_transaction.add_conflict(lsu_forward_transaction, priority=Priority.LEFT)

        with Transaction().body(m, request=atomic_in_progress & atomic_second_reqest & ~atomic_fin):
            atomic_store_op = Signal(self.fu_layouts.issue)
            m.d.av_comb += assign(atomic_store_op, atomic_op)
            m.d.av_comb += assign(atomic_store_op.exec_fn, {"op_type": OpType.STORE, "funct3": Funct3.W})
            m.d.av_comb += atomic_store_op.imm.eq(0)
            m.d.av_comb += atomic_store_op.s2_val.eq(atomic_op_res(load_val, atomic_op.s2_val))

            self.lsu.issue(m, atomic_store_op)

            m.d.sync += atomic_fin.eq(1)

        m.submodules.accept_forwarder = accept_forwarder
        m.submodules.atomic_res_fifo = atomic_res_fifo
        m.submodules.lsu = self.lsu

        return m


@dataclass(frozen=True)
class LSUAtomicWrapperComponent(FunctionalComponentParams):
    lsu: LSUComponent

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return LSUAtomicWrapper(gen_params, self.lsu.get_module(gen_params))

    def get_optypes(self) -> set[OpType]:
        return {OpType.ATOMIC_MEMORY_OP} | self.lsu.get_optypes()
