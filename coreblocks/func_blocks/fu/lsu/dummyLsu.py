from dataclasses import dataclass

from amaranth import *
from transactron import Method, TModule, Transaction, def_method
from transactron.lib import BasicFifo
from transactron.lib.connectors import FIFO
from transactron.lib.logging import HardwareLogger
from transactron.lib.simultaneous import condition
from transactron.utils import DependencyContext
from transactron.utils.transactron_helpers import make_layout

from coreblocks.arch import OpType
from coreblocks.cache.dcache import DCache, DCacheBypass
from coreblocks.cache.iface import CacheInterface
from coreblocks.cache.refiller import SimpleCommonBusDataCacheRefiller
from coreblocks.arch.isa_consts import ExceptionCause
from coreblocks.frontend.decoder import *
from coreblocks.func_blocks.fu.lsu.lsu_requester import LSURequester
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker
from coreblocks.func_blocks.fu.lsu.pmp import PMPChecker
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.interface.keys import (
    CommonBusDataKey,
    CoreStateKey,
    CSRInstancesKey,
    ExceptionReportKey,
    InstructionPrecommitKey,
)
from coreblocks.interface.layouts import DCacheLayouts, FuncUnitLayouts, LSULayouts
from coreblocks.params import *
from coreblocks.peripherals.bus_adapter import BusMasterInterface

__all__ = ["LSUDummy", "LSUComponent"]


class LSUDataPathRouter(Elaboratable, CacheInterface):
    def __init__(self, gen_params: GenParams, cached_data_path: CacheInterface, mmio_data_path: CacheInterface) -> None:
        self.gen_params = gen_params
        layouts = gen_params.get(DCacheLayouts)

        self.cached_data_path = cached_data_path
        self.mmio_data_path = mmio_data_path

        self.issue_req = Method(i=layouts.issue_req)
        self.accept_res = Method(o=layouts.accept_res)
        self.flush = Method()

    def elaborate(self, platform):
        m = TModule()

        m.submodules.pma_checker = pma_checker = PMAChecker(self.gen_params)
        m.submodules.mmio_fifo = mmio_fifo = BasicFifo([("mmio", 1)], self.gen_params.dcache_params.request_depth)

        @def_method(m, self.issue_req)
        def _(addr: Value, data: Value, byte_mask: Value, store: Value):
            m.d.av_comb += pma_checker.addr.eq(addr)

            with condition(m) as branch:
                with branch(pma_checker.result["mmio"]):
                    self.mmio_data_path.issue_req(m, addr=addr, data=data, byte_mask=byte_mask, store=store)
                with branch():
                    self.cached_data_path.issue_req(m, addr=addr, data=data, byte_mask=byte_mask, store=store)

            mmio_fifo.write(m, mmio=pma_checker.result["mmio"])

        @def_method(m, self.accept_res)
        def _():
            route = mmio_fifo.read(m)
            response = Signal(self.gen_params.get(DCacheLayouts).accept_res)

            with condition(m) as branch:
                with branch(route.mmio):
                    m.d.comb += response.eq(self.mmio_data_path.accept_res(m))
                with branch():
                    m.d.comb += response.eq(self.cached_data_path.accept_res(m))

            return response

        @def_method(m, self.flush)
        def _() -> None:
            self.cached_data_path.flush(m)
            self.mmio_data_path.flush(m)

        return m


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

        csr = self.dependency_manager.get_dependency(CSRInstancesKey())
        m.submodules.pma_checker = pma_checker = PMAChecker(self.gen_params)
        m.submodules.pmp_checker = pmp_checker = PMPChecker(self.gen_params, csr.m_mode)

        dcache_layouts = self.gen_params.get(DCacheLayouts)
        if self.gen_params.dcache_params.enable:
            m.submodules.dcache_refiller = dcache_refiller = SimpleCommonBusDataCacheRefiller(
                dcache_layouts, self.gen_params.dcache_params, self.bus
            )
            m.submodules.cached_data_path = cached_data_path = DCache(
                dcache_layouts, self.gen_params.dcache_params, dcache_refiller
            )
            dcache_refiller.get_writeback_data.provide(cached_data_path.provide_writeback_data)
        else:
            m.submodules.cached_data_path = cached_data_path = DCacheBypass(
                dcache_layouts, self.gen_params.dcache_params, self.bus
            )

        m.submodules.mmio_data_path = mmio_data_path = DCacheBypass(
            dcache_layouts, self.gen_params.dcache_params, self.bus
        )
        m.submodules.data_path_router = data_path_router = LSUDataPathRouter(
            self.gen_params, cached_data_path, mmio_data_path
        )
        m.submodules.requester = requester = LSURequester(self.gen_params, data_path_router)

        request_layout = make_layout(
            ("data", self.fu_layouts.issue),
            ("addr", self.gen_params.isa.xlen),
        )
        m.submodules.requests = requests = FIFO(request_layout, 2)
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
                requests.write(m, data=arg, addr=addr)
            with m.Else():
                results_noop.write(m, data=0, exception=0, cause=0, addr=0)
                issued_noop.write(m, arg)

        # Issues load/store requests when the instruction is known, is a LOAD/STORE, and just before commit.
        # Memory loads can be issued speculatively.
        pmas = pma_checker.result
        can_reorder = is_load & ~pmas["mmio"]
        want_issue = rob_id_match | can_reorder

        do_issue = ~flush & want_issue
        with Transaction().body(m, ready=do_issue):
            req = requests.read(m)
            arg = req.data
            addr = req.addr

            m.d.av_comb += pma_checker.addr.eq(addr)
            m.d.av_comb += pmp_checker.addr.eq(addr)
            m.d.av_comb += is_load.eq(arg.exec_fn.op_type == OpType.LOAD)
            m.d.av_comb += request_rob_id.eq(arg.rob_id)

            pmp_exception = Signal()
            pmp_cause = Signal(ExceptionCause)

            with m.If(is_load & ~pmp_checker.result.r):
                m.d.av_comb += pmp_exception.eq(1)
                m.d.av_comb += pmp_cause.eq(ExceptionCause.LOAD_ACCESS_FAULT)
            with m.Elif(~is_load & ~pmp_checker.result.w):
                m.d.av_comb += pmp_exception.eq(1)
                m.d.av_comb += pmp_cause.eq(ExceptionCause.STORE_ACCESS_FAULT)

            with m.If(~pmp_exception):
                res = requester.issue(
                    m,
                    addr=addr,
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
                results_noop.write(m, data=0, exception=1, cause=pmp_cause, addr=addr)

        # Handles flushed instructions as a no-op.
        with Transaction().body(m, ready=flush):
            req = requests.read(m)
            results_noop.write(m, data=0, exception=0, cause=0, addr=0)
            issued_noop.write(m, req.data)

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
