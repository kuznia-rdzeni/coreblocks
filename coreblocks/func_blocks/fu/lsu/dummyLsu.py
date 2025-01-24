from dataclasses import dataclass
from amaranth import *

from transactron import Method, def_method, Transaction, TModule
from transactron.lib.connectors import FIFO, Forwarder
from transactron.utils import DependencyContext
from transactron.lib.simultaneous import condition
from transactron.lib.logging import HardwareLogger

from coreblocks.params import *
from coreblocks.arch import OpType
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.frontend.decoder import *
from coreblocks.interface.layouts import LSULayouts, FuncUnitLayouts
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker
from coreblocks.func_blocks.fu.lsu.lsu_requester import LSURequester
from coreblocks.interface.keys import CoreStateKey, ExceptionReportKey, CommonBusDataKey, InstructionPrecommitKey

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

        self.dependency_manager = DependencyContext.get()
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.issue = Method(i=self.fu_layouts.issue)
        self.accept = Method(o=self.fu_layouts.accept)

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

        m.submodules.pma_checker = pma_checker = PMAChecker(self.gen_params)
        m.submodules.requester = requester = LSURequester(self.gen_params, self.bus)

        m.submodules.requests = requests = Forwarder(self.fu_layouts.issue)
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
                requests.write(m, arg)
            with m.Else():
                results_noop.write(m, data=0, exception=0, cause=0, addr=0)
                issued_noop.write(m, arg)

        # Issues load/store requests when the instruction is known, is a LOAD/STORE, and just before commit.
        # Memory loads can be issued speculatively.
        pmas = pma_checker.result
        can_reorder = is_load & ~pmas["mmio"]
        want_issue = rob_id_match | can_reorder

        do_issue = ~flush & want_issue
        with Transaction().body(m, request=do_issue):
            arg = requests.read(m)

            addr = Signal(self.gen_params.isa.xlen)
            m.d.av_comb += addr.eq(arg.s1_val + arg.imm)
            m.d.av_comb += pma_checker.addr.eq(addr)
            m.d.av_comb += is_load.eq(arg.exec_fn.op_type == OpType.LOAD)
            m.d.av_comb += request_rob_id.eq(arg.rob_id)

            res = requester.issue(
                m,
                addr=addr,
                data=arg.s2_val,
                funct3=arg.exec_fn.funct3,
                store=~is_load,
            )

            with m.If(res["exception"]):
                issued_noop.write(m, arg)
                results_noop.write(m, data=0, exception=res["exception"], cause=res["cause"], addr=addr)
            with m.Else():
                issued.write(m, arg)

        # Handles flushed instructions as a no-op.
        with Transaction().body(m, request=flush):
            arg = requests.read(m)
            results_noop.write(m, data=0, exception=0, cause=0, addr=0)
            issued_noop.write(m, arg)

        @def_method(m, self.accept)
        def _():
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

            return {
                "rob_id": arg["rob_id"],
                "rp_dst": arg["rp_dst"],
                "result": res["data"],
                "exception": res["exception"],
            }

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

    def get_decoder_manager(self):
        pass  # LSU component currently doesn't have a decoder manager

    def get_optypes(self) -> set[OpType]:
        return {OpType.LOAD, OpType.STORE, OpType.FENCE}
