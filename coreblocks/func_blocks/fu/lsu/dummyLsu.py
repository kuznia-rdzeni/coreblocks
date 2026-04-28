from dataclasses import dataclass

from amaranth import *
from transactron import Method, TModule, Transaction, def_method
from transactron.lib.connectors import FIFO, ConnectTrans
from transactron.lib.logging import HardwareLogger
from transactron.lib.simultaneous import condition
from transactron.utils import DependencyContext

from coreblocks.arch import OpType
from coreblocks.arch.isa_consts import ExceptionCause
from coreblocks.func_blocks.fu.lsu.lsu_requester import LSURequester
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker
from coreblocks.priv.pmp import PMPChecker, PMPOperationMode
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.keys import (
    CommonBusDataKey,
    CoreStateKey,
    ExceptionReportKey,
    InstructionPrecommitKey,
)
from coreblocks.interface.layouts import FuncUnitLayouts, LSULayouts, AddressTranslationLayouts
from coreblocks.params import *
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.priv.vmem.translation import AddressTranslator, AddressTranslatorMode

__all__ = ["LSUDummy", "LSUComponent"]


class LSUDummy(FuncUnit, Elaboratable):
    """
    Very simple LSU, which serializes all stores and loads.
    It isn't fully compliant with RiscV spec. Doesn't support checking if
    address is in correct range. Addresses have to be aligned.
    """

    def __init__(self, gen_params: GenParams, bus: BusMasterInterface) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Parameters to be used during processor generation.
        bus : BusMasterInterface
            An instance of the bus master for interfacing with the data bus.
        """

        self.gen_params = gen_params
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.lsu_layouts = gen_params.get(LSULayouts)
        self.translator_layouts = gen_params.get(AddressTranslationLayouts)

        self.dependency_manager = DependencyContext.get()
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())()

        self.issue = Method(i=self.fu_layouts.issue)
        self.push_result = Method(i=self.fu_layouts.push_result)

        self.bus = bus

        self.log = HardwareLogger("backend.lsu.dummylsu")

    def elaborate(self, platform):
        m = TModule()
        flush = Signal()  # exception handling, requests are not issued

        with Transaction().body(m):
            core_state = self.dependency_manager.get_dependency(CoreStateKey())
            state = core_state(m)
            m.d.comb += flush.eq(state.flushing)

        # Signals for handling issue logic
        request_rob_id = Signal(self.gen_params.rob_entries_bits)
        rob_id_match = Signal()
        is_load = Signal()

        m.submodules.addr_translator = addr_translator = AddressTranslator(
            self.gen_params, mode=AddressTranslatorMode.LSU
        )
        m.submodules.pma_checker = pma_checker = PMAChecker(self.gen_params)
        m.submodules.pmp_checker = pmp_checker = PMPChecker(self.gen_params, mode=PMPOperationMode.LSU)
        m.submodules.requester = requester = LSURequester(self.gen_params, self.bus)

        m.submodules.requests = requests = FIFO(self.fu_layouts.issue, 2)
        m.submodules.translated = translated = FIFO(self.translator_layouts.accept, 2)
        m.submodules.results_noop = results_noop = FIFO(self.lsu_layouts.accept, 2)
        m.submodules.issued = issued = FIFO(self.fu_layouts.issue, 2)
        m.submodules.issued_noop = issued_noop = FIFO(self.fu_layouts.issue, 2)

        @def_method(m, self.issue)
        def _(arg):
            self.log.debug(
                m, 1, "issue rob_id={} funct3={} op_type={}", arg.rob_id, arg.exec_fn.funct3, arg.exec_fn.op_type
            )
            is_fence = arg.exec_fn.op_type == OpType.FENCE
            with m.If(~is_fence):
                addr = Signal(self.gen_params.isa.xlen)
                m.d.av_comb += addr.eq(arg.s1_val + arg.imm)

                addr_translator.request(m, addr=addr)
                requests.write(m, arg)
            with m.Else():
                results_noop.write(m, data=0, exception=0, cause=0, addr=0)
                issued_noop.write(m, arg)

        m.submodules += ConnectTrans.create(addr_translator.accept, translated.write)

        # Issues load/store requests when the instruction is known, is a LOAD/STORE, and just before commit.
        # Memory loads can be issued speculatively.
        pmas = pma_checker.result
        can_reorder = is_load & ~pmas["mmio"]
        want_issue = rob_id_match | can_reorder

        do_issue = ~flush & want_issue
        with Transaction().body(m, ready=do_issue):
            arg = requests.read(m)
            translated_req = translated.read(m)
            paddr = translated_req.paddr
            addr = translated_req.vaddr

            m.d.av_comb += pma_checker.paddr.eq(paddr)
            m.d.av_comb += pmp_checker.paddr.eq(paddr)
            m.d.av_comb += is_load.eq(arg.exec_fn.op_type == OpType.LOAD)
            m.d.av_comb += request_rob_id.eq(arg.rob_id)

            exception = Signal()
            cause = Signal(ExceptionCause)

            with m.If(translated_req.page_fault):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(Mux(is_load, ExceptionCause.LOAD_PAGE_FAULT, ExceptionCause.STORE_PAGE_FAULT))
            with m.Elif(translated_req.access_fault):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(
                    Mux(is_load, ExceptionCause.LOAD_ACCESS_FAULT, ExceptionCause.STORE_ACCESS_FAULT)
                )
            with m.Elif(is_load & ~pmp_checker.result.r):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(ExceptionCause.LOAD_ACCESS_FAULT)
            with m.Elif(~is_load & ~pmp_checker.result.w):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(ExceptionCause.STORE_ACCESS_FAULT)

            with m.If(~exception):
                res = requester.issue(
                    m,
                    paddr=paddr,
                    vaddr=addr,
                    data=arg.s2_val,
                    funct3=arg.exec_fn.funct3,
                    store=~is_load,
                )
                with m.If(res["exception"]):
                    issued_noop.write(m, arg)
                    results_noop.write(m, data=0, exception=1, cause=res["cause"], addr=addr)
                with m.Else():
                    issued.write(m, arg)
            with m.Else():
                issued_noop.write(m, arg)
                results_noop.write(m, data=0, exception=1, cause=cause, addr=addr)

        # Handles flushed instructions as a no-op.
        with Transaction().body(m, ready=flush):
            arg = requests.read(m)
            translated.read(m)
            results_noop.write(m, data=0, exception=0, cause=0, addr=0)
            issued_noop.write(m, arg)

        with Transaction().body(m):
            arg = Signal(self.fu_layouts.issue)
            res = Signal(self.lsu_layouts.accept)
            with condition(m) as branch:
                with branch(True):
                    m.d.comb += res.eq(requester.accept(m))
                    m.d.comb += arg.eq(issued.read(m))
                with branch(True):
                    m.d.comb += res.eq(results_noop.read(m))
                    m.d.comb += arg.eq(issued_noop.read(m))

            with m.If(res["exception"]):
                self.report(m, rob_id=arg["rob_id"], cause=res["cause"], pc=arg["pc"], mtval=res["addr"])

            self.log.debug(m, 1, "accept rob_id={} result=0x{:08x} exception={}", arg.rob_id, res.data, res.exception)

            self.push_result(
                m,
                rob_id=arg["rob_id"],
                rp_dst=arg["rp_dst"],
                result=res["data"],
                exception=res["exception"],
            )

        with Transaction().body(m):
            precommit = self.dependency_manager.get_dependency(InstructionPrecommitKey())
            precommit(m, request_rob_id)
            m.d.comb += rob_id_match.eq(1)

        return m


@dataclass(frozen=True)
class LSUComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        connections = DependencyContext.get()
        bus_master = connections.get_dependency(CommonBusDataKey())
        unit = LSUDummy(gen_params, bus_master)
        return unit

    def get_decoder_manager(self):  # type: ignore
        pass  # LSU component currently doesn't have a decoder manager

    def get_optypes(self) -> set[OpType]:
        return {OpType.LOAD, OpType.STORE, OpType.FENCE}
