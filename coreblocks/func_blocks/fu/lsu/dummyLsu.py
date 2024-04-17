from dataclasses import dataclass
from amaranth import *

from transactron import Method, def_method, Transaction, TModule
from transactron.lib.connectors import FIFO, Forwarder
from transactron.utils import ModuleLike, DependencyManager
from transactron.lib.simultaneous import condition
from transactron.lib.logging import HardwareLogger

from coreblocks.params import *
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.frontend.decoder import *
from coreblocks.interface.layouts import LSULayouts, FuncUnitLayouts
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.func_blocks.fu.lsu.pma import PMAChecker
from coreblocks.interface.keys import ExceptionReportKey, CommonBusDataKey, InstructionPrecommitKey

__all__ = ["LSUDummy", "LSUComponent"]


class LSURequester(Elaboratable):
    """
    Bus request logic for the load/store unit. Its job is to interface
    between the LSU and the bus.

    Attributes
    ----------
    issue : Method
        Issues a new request to the bus.
    accept : Method
        Retrieves a result from the bus.
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
        self.bus = bus

        lsu_layouts = gen_params.get(LSULayouts)

        self.issue = Method(i=lsu_layouts.issue, o=lsu_layouts.issue_out)
        self.accept = Method(o=lsu_layouts.accept)

        self.log = HardwareLogger("backend.lsu.requester")

    def prepare_bytes_mask(self, m: ModuleLike, funct3: Value, addr: Value) -> Signal:
        mask_len = self.gen_params.isa.xlen // self.bus.params.granularity
        mask = Signal(mask_len)
        with m.Switch(funct3):
            with m.Case(Funct3.B, Funct3.BU):
                m.d.av_comb += mask.eq(0x1 << addr[0:2])
            with m.Case(Funct3.H, Funct3.HU):
                m.d.av_comb += mask.eq(0x3 << (addr[1] << 1))
            with m.Case(Funct3.W):
                m.d.av_comb += mask.eq(0xF)
        return mask

    def postprocess_load_data(self, m: ModuleLike, funct3: Value, raw_data: Value, addr: Value):
        data = Signal.like(raw_data)
        with m.Switch(funct3):
            with m.Case(Funct3.B, Funct3.BU):
                tmp = Signal(8)
                m.d.av_comb += tmp.eq((raw_data >> (addr[0:2] << 3)) & 0xFF)
                with m.If(funct3 == Funct3.B):
                    m.d.av_comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.av_comb += data.eq(tmp)
            with m.Case(Funct3.H, Funct3.HU):
                tmp = Signal(16)
                m.d.av_comb += tmp.eq((raw_data >> (addr[1] << 4)) & 0xFFFF)
                with m.If(funct3 == Funct3.H):
                    m.d.av_comb += data.eq(tmp.as_signed())
                with m.Else():
                    m.d.av_comb += data.eq(tmp)
            with m.Default():
                m.d.av_comb += data.eq(raw_data)
        return data

    def prepare_data_to_save(self, m: ModuleLike, funct3: Value, raw_data: Value, addr: Value):
        data = Signal.like(raw_data)
        with m.Switch(funct3):
            with m.Case(Funct3.B):
                m.d.av_comb += data.eq(raw_data[0:8] << (addr[0:2] << 3))
            with m.Case(Funct3.H):
                m.d.av_comb += data.eq(raw_data[0:16] << (addr[1] << 4))
            with m.Default():
                m.d.av_comb += data.eq(raw_data)
        return data

    def check_align(self, m: TModule, funct3: Value, addr: Value):
        aligned = Signal()
        with m.Switch(funct3):
            with m.Case(Funct3.W):
                m.d.av_comb += aligned.eq(addr[0:2] == 0)
            with m.Case(Funct3.H, Funct3.HU):
                m.d.av_comb += aligned.eq(addr[0] == 0)
            with m.Default():
                m.d.av_comb += aligned.eq(1)
        return aligned

    def elaborate(self, platform):
        m = TModule()

        addr_reg = Signal(self.gen_params.isa.xlen)
        funct3_reg = Signal(Funct3)
        store_reg = Signal()
        request_sent = Signal()

        @def_method(m, self.issue, ~request_sent)
        def _(addr: Value, data: Value, funct3: Value, store: Value):
            exception = Signal()
            cause = Signal(ExceptionCause)

            aligned = self.check_align(m, funct3, addr)
            bytes_mask = self.prepare_bytes_mask(m, funct3, addr)
            bus_data = self.prepare_data_to_save(m, funct3, data, addr)

            self.log.debug(
                m,
                1,
                "issue addr=0x{:08x} data=0x{:08x} funct3={} store={} aligned={}",
                addr,
                data,
                funct3,
                store,
                aligned,
            )

            with condition(m, nonblocking=False, priority=False) as branch:
                with branch(aligned & store):
                    self.bus.request_write(m, addr=addr >> 2, data=bus_data, sel=bytes_mask)
                with branch(aligned & ~store):
                    self.bus.request_read(m, addr=addr >> 2, sel=bytes_mask)
                with branch(~aligned):
                    pass

            with m.If(aligned):
                m.d.sync += request_sent.eq(1)
                m.d.sync += addr_reg.eq(addr)
                m.d.sync += funct3_reg.eq(funct3)
                m.d.sync += store_reg.eq(store)
            with m.Else():
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(
                    Mux(store, ExceptionCause.STORE_ADDRESS_MISALIGNED, ExceptionCause.LOAD_ADDRESS_MISALIGNED)
                )

            return {"exception": exception, "cause": cause}

        @def_method(m, self.accept, request_sent)
        def _():
            data = Signal(self.gen_params.isa.xlen)
            exception = Signal()
            cause = Signal(ExceptionCause)
            err = Signal()

            self.log.debug(m, 1, "accept data=0x{:08x} exception={} cause={}", data, exception, cause)

            with condition(m, nonblocking=False, priority=False) as branch:
                with branch(store_reg):
                    fetched = self.bus.get_write_response(m)
                    m.d.comb += err.eq(fetched.err)
                with branch(~store_reg):
                    fetched = self.bus.get_read_response(m)
                    m.d.comb += err.eq(fetched.err)
                    m.d.top_comb += data.eq(self.postprocess_load_data(m, funct3_reg, fetched.data, addr_reg))

            m.d.sync += request_sent.eq(0)

            with m.If(err):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(
                    Mux(store_reg, ExceptionCause.STORE_ACCESS_FAULT, ExceptionCause.LOAD_ACCESS_FAULT)
                )

            return {"data": data, "exception": exception, "cause": cause}

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

        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.issue = Method(i=self.fu_layouts.issue, single_caller=True)
        self.accept = Method(o=self.fu_layouts.accept)

        self.bus = bus

    def elaborate(self, platform):
        m = TModule()
        flush = Signal()  # exception handling, requests are not issued

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
            is_fence = arg.exec_fn.op_type == OpType.FENCE
            with m.If(~is_fence):
                requests.write(m, arg)
            with m.Else():
                results_noop.write(m, data=0, exception=0, cause=0)
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
                results_noop.write(m, data=0, exception=res["exception"], cause=res["cause"])
            with m.Else():
                issued.write(m, arg)

        # Handles flushed instructions as a no-op.
        with Transaction().body(m, request=flush):
            arg = requests.read(m)
            results_noop.write(m, data=0, exception=0, cause=0)
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
                self.report(m, rob_id=arg["rob_id"], cause=res["cause"], pc=arg["pc"])

            return {
                "rob_id": arg["rob_id"],
                "rp_dst": arg["rp_dst"],
                "result": res["data"],
                "exception": res["exception"],
            }

        with Transaction().body(m):
            precommit = self.dependency_manager.get_dependency(InstructionPrecommitKey())
            info = precommit(m)
            with m.If(info.rob_id == request_rob_id):
                m.d.comb += rob_id_match.eq(1)
            with m.If(~info.side_fx):
                m.d.comb += flush.eq(1)

        return m


@dataclass(frozen=True)
class LSUComponent(FunctionalComponentParams):
    def get_module(self, gen_params: GenParams) -> FuncUnit:
        connections = gen_params.get(DependencyManager)
        bus_master = connections.get_dependency(CommonBusDataKey())
        unit = LSUDummy(gen_params, bus_master)
        return unit

    def get_optypes(self) -> set[OpType]:
        return {OpType.LOAD, OpType.STORE, OpType.FENCE}
