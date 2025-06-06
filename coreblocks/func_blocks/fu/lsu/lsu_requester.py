from amaranth import *
from transactron import Method, def_method, TModule
from transactron.utils import ModuleLike
from transactron.lib.simultaneous import condition
from transactron.lib.logging import HardwareLogger
from transactron.lib import BasicFifo

from coreblocks.params import *
from coreblocks.arch import Funct3, ExceptionCause
from coreblocks.peripherals.bus_adapter import BusMasterInterface
from coreblocks.interface.layouts import LSULayouts
from coreblocks.func_blocks.fu.lsu.pmp import PMPChecker


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

    def __init__(self, gen_params: GenParams, bus: BusMasterInterface, depth: int = 4) -> None:
        """
        Parameters
        ----------
        gen_params : GenParams
            Parameters to be used during processor generation.
        bus : BusMasterInterface
            An instance of the bus master for interfacing with the data bus.
        depth : int
            Number of requests which can be send to memory, before it provides first response. Describe
            the resiliency of `LSURequester` to latency of memory in case when memory is fully pipelined.
        """
        self.gen_params = gen_params
        self.bus = bus
        self.depth = depth

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

        m.submodules.args_fifo = args_fifo = BasicFifo(
            [("addr", self.gen_params.isa.xlen), ("funct3", Funct3), ("store", 1)], self.depth
        )
        m.submodules.pmp_checker = pmp_checker = PMPChecker(self.gen_params)

        @def_method(m, self.issue)
        def _(addr: Value, data: Value, funct3: Value, store: Value):
            exception = Signal()
            cause = Signal(ExceptionCause)

            aligned = self.check_align(m, funct3, addr)
            bytes_mask = self.prepare_bytes_mask(m, funct3, addr)
            bus_data = self.prepare_data_to_save(m, funct3, data, addr)
            pmps = pmp_checker.result
            m.d.av_comb += pmp_checker.addr.eq(addr)
            has_permission = Mux(store, pmps["w"], pmps["r"])

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

            with condition(m, nonblocking=True) as branch:
                with branch(aligned & store):
                    self.bus.request_write(m, addr=addr >> 2, data=bus_data, sel=bytes_mask)
                with branch(aligned & ~store):
                    self.bus.request_read(m, addr=addr >> 2, sel=bytes_mask)

            with m.If(~aligned):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(
                    Mux(store, ExceptionCause.STORE_ADDRESS_MISALIGNED, ExceptionCause.LOAD_ADDRESS_MISALIGNED)
                )
            with m.Elif(~has_permission):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(Mux(store, ExceptionCause.STORE_ACCESS_FAULT, ExceptionCause.LOAD_ACCESS_FAULT))
            with m.Else():
                args_fifo.write(m, addr=addr, funct3=funct3, store=store)

            return {"exception": exception, "cause": cause}

        @def_method(m, self.accept)
        def _():
            data = Signal(self.gen_params.isa.xlen)
            exception = Signal()
            cause = Signal(ExceptionCause)
            err = Signal()

            request_args = args_fifo.read(m)
            self.log.debug(m, 1, "accept data=0x{:08x} exception={} cause={}", data, exception, cause)

            with condition(m) as branch:
                with branch(request_args.store):
                    fetched = self.bus.get_write_response(m)
                    m.d.comb += err.eq(fetched.err)
                with branch():
                    fetched = self.bus.get_read_response(m)
                    m.d.comb += err.eq(fetched.err)
                    m.d.top_comb += data.eq(
                        self.postprocess_load_data(m, request_args.funct3, fetched.data, request_args.addr)
                    )

            with m.If(err):
                m.d.av_comb += exception.eq(1)
                m.d.av_comb += cause.eq(
                    Mux(request_args.store, ExceptionCause.STORE_ACCESS_FAULT, ExceptionCause.LOAD_ACCESS_FAULT)
                )

            return {"data": data, "exception": exception, "cause": cause, "addr": request_args.addr}

        return m
