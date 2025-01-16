from amaranth import *

from dataclasses import dataclass

from transactron.core import Priority, TModule, Method, Transaction, def_method
from transactron.lib.connectors import Forwarder
from transactron.utils import assign, layout_subset, AssignType

from coreblocks.arch import Funct3, Funct7, OpType
from coreblocks.func_blocks.fu.lsu.dummyLsu import LSUComponent
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.params import GenParams, FunctionalComponentParams


class LSUAtomicWrapper(FuncUnit, Elaboratable):
    """
    Wrapper for LSU that adds support for atomic operations.

    It provides simplified implementation of atomic operations under assumptions that:
        * LSU doesn't reorder memory accesses, like in `LSUDummy`
        * There is only one hart

    AMO operations issue two independent accesses (unless there is an exception) to LSU and execute operations
    in the internal ALU.
    SC are only matched to LR, reservation set size is infinite.

    Behaviour of atomic insturctions on Memory Mapped I/O space is currently undefined.
    """

    def __init__(self, gen_params: GenParams, lsu: FuncUnit):
        self.gen_params = gen_params
        self.lsu = lsu

        self.fu_layouts = fu_layouts = gen_params.get(FuncUnitLayouts)
        self.issue = Method(i=fu_layouts.issue)
        self.accept = Method(o=fu_layouts.accept)

    def elaborate(self, platform):
        m = TModule()

        # Simplified due to no other harts, reservation set size == adress space (implementation defined)
        reservation_valid = Signal()

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

        atomic_is_lr_sc = Signal()
        sc_failed = Signal()

        @def_method(m, self.issue, ready=~atomic_in_progress)
        def _(arg):
            is_amo = arg.exec_fn.op_type == OpType.ATOMIC_MEMORY_OP
            is_lr_sc = arg.exec_fn.op_type == OpType.ATOMIC_LR_SC

            issue_store = Signal()
            sc_fail = Signal()

            funct7 = arg.exec_fn.funct7 & ~0b11
            with m.If(is_lr_sc & (funct7 == Funct7.LR)):
                m.d.sync += reservation_valid.eq(1)
            with m.Elif(is_lr_sc & (funct7 == Funct7.SC)):
                m.d.sync += reservation_valid.eq(0)
                m.d.av_comb += issue_store.eq(1)
                m.d.av_comb += sc_fail.eq(~reservation_valid)

            atomic_issue_op = Signal(self.fu_layouts.issue)
            m.d.av_comb += assign(atomic_issue_op, arg)
            m.d.av_comb += assign(
                atomic_issue_op.exec_fn,
                {
                    "op_type": Mux(issue_store, OpType.STORE, OpType.LOAD),
                    "funct3": Funct3.W,
                },
            )
            m.d.av_comb += atomic_issue_op.imm.eq(0)

            with m.If((is_amo | is_lr_sc) & ~sc_fail):
                self.lsu.issue(m, atomic_issue_op)
            with m.Elif(~sc_fail):
                self.lsu.issue(m, arg)

            with m.If(is_amo | is_lr_sc):
                m.d.sync += atomic_in_progress.eq(1)
                m.d.sync += atomic_is_lr_sc.eq(is_lr_sc)
                m.d.sync += assign(atomic_op, arg, fields=AssignType.LHS)

            m.d.sync += sc_failed.eq(sc_fail)

        @def_method(m, self.accept)
        def _():
            return accept_forwarder.read(m)

        atomic_second_reqest = Signal()
        atomic_fin = Signal()

        with Transaction().body(m) as accept_trans:
            res = self.lsu.accept(m)

            funct7 = atomic_op.exec_fn.funct7 & ~0b11

            # LR/SC
            with m.If((res.rob_id == atomic_op.rob_id) & atomic_in_progress & atomic_is_lr_sc):
                atomic_res = Signal(self.fu_layouts.accept)
                m.d.av_comb += assign(atomic_res, res)
                with m.If(funct7 == Funct7.SC):
                    m.d.av_comb += atomic_res.result.eq(0)

                with m.If(res.exception):
                    m.d.sync += reservation_valid.eq(0)

                accept_forwarder.write(m, atomic_res)
                m.d.sync += atomic_in_progress.eq(0)

            # 1st AMO result
            with m.Elif((res.rob_id == atomic_op.rob_id) & atomic_in_progress & ~atomic_second_reqest & ~res.exception):
                # NOTE: This branch could be optimised by replacing Ifs with condition to be independent of
                # accept.ready, but it causes combinational loop because of `rob_id` data dependency.
                m.d.sync += load_val.eq(res.result)
                m.d.sync += atomic_second_reqest.eq(1)
            with m.Elif((res.rob_id == atomic_op.rob_id) & atomic_in_progress & ~atomic_second_reqest & res.exception):
                accept_forwarder.write(m, res)
                m.d.sync += atomic_in_progress.eq(0)

            # 2nd AMO result
            with m.Elif(atomic_in_progress & atomic_fin):
                atomic_res = Signal(self.fu_layouts.accept)
                m.d.av_comb += assign(atomic_res, res)
                m.d.av_comb += atomic_res.result.eq(Mux(res.exception, 0, load_val))
                accept_forwarder.write(m, atomic_res)

                m.d.sync += atomic_in_progress.eq(0)
                m.d.sync += atomic_second_reqest.eq(0)
                m.d.sync += atomic_fin.eq(0)

            # Non-atomic results
            with m.Else():
                accept_forwarder.write(m, res)

        with Transaction().body(m, request=atomic_in_progress & atomic_second_reqest & ~atomic_fin):
            atomic_store_op = Signal(self.fu_layouts.issue)
            m.d.av_comb += assign(atomic_store_op, atomic_op)
            m.d.av_comb += assign(atomic_store_op.exec_fn, {"op_type": OpType.STORE, "funct3": Funct3.W})
            m.d.av_comb += atomic_store_op.imm.eq(0)
            m.d.av_comb += atomic_store_op.s2_val.eq(atomic_op_res(load_val, atomic_op.s2_val))

            self.lsu.issue(m, atomic_store_op)

            m.d.sync += atomic_fin.eq(1)

        with Transaction().body(m, request=atomic_in_progress & sc_failed) as sc_failed_trans:
            m.d.sync += sc_failed.eq(0)
            m.d.sync += atomic_in_progress.eq(0)
            accept_forwarder.write(
                m,
                {
                    "result": 1,
                    "rob_id": atomic_op.rob_id,
                    "rp_dst": atomic_op.rp_dst,
                    "exception": 0,
                },
            )

        sc_failed_trans.add_conflict(accept_trans, priority=Priority.RIGHT)

        m.submodules.accept_forwarder = accept_forwarder
        m.submodules.lsu = self.lsu

        return m


@dataclass(frozen=True)
class LSUAtomicWrapperComponent(FunctionalComponentParams):
    lsu: LSUComponent

    def get_module(self, gen_params: GenParams) -> FuncUnit:
        return LSUAtomicWrapper(gen_params, self.lsu.get_module(gen_params))

    def get_optypes(self) -> set[OpType]:
        return {OpType.ATOMIC_MEMORY_OP, OpType.ATOMIC_LR_SC} | self.lsu.get_optypes()
