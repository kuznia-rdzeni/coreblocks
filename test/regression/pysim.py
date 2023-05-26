from amaranth.sim import Passive, Settle
from amaranth.utils import log2_int

from .memory import *
from .common import SimulationBackend

from ..common import SimpleTestCircuit, PysimSimulator
from ..peripherals.test_wishbone import WishboneInterfaceWrapper

from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.params.configurations import full_core_config
from coreblocks.peripherals.wishbone import WishboneBus


class PySimulation(SimulationBackend):
    def __init__(self, verbose: bool, traces_file: Optional[str] = None):
        self.gp = GenParams(full_core_config)
        self.running = False
        self.cycle_cnt = 0
        self.verbose = verbose
        self.traces_file = traces_file

    def _wishbone_slave(
        self, mem_model: CoreMemoryModel, wb_ctrl: WishboneInterfaceWrapper, is_instr_bus: bool, delay: int = 0
    ):
        def f():
            yield Passive()

            while True:
                yield from wb_ctrl.slave_wait()

                word_width_bytes = self.gp.isa.xlen // 8

                # Wishbone is addressing words, so we need to shift it a bit to get the real address.
                addr = (yield wb_ctrl.wb.adr) << log2_int(word_width_bytes)
                sel = yield wb_ctrl.wb.sel
                dat_w = yield wb_ctrl.wb.dat_w

                resp_data = 0

                bus_name = "instr" if is_instr_bus else "data"

                if (yield wb_ctrl.wb.we):
                    if self.verbose:
                        print(f"Wishbone '{bus_name}' bus write request: addr=0x{addr:x} data={dat_w:x} sel={sel:b}")
                    resp = mem_model.write(
                        WriteRequest(addr=addr, data=dat_w, byte_count=word_width_bytes, byte_sel=sel)
                    )
                else:
                    if self.verbose:
                        print(f"Wishbone '{bus_name}' bus read request: addr=0x{addr:x} sel={sel}")
                    resp = mem_model.read(
                        ReadRequest(
                            addr=addr,
                            byte_count=word_width_bytes,
                            byte_sel=sel,
                            exec=is_instr_bus,
                        )
                    )
                    resp_data = resp.data

                ack = err = rty = 0
                match resp.status:
                    case ReplyStatus.OK:
                        ack = 1
                    case ReplyStatus.ERROR:
                        err = 1
                    case ReplyStatus.RETRY:
                        rty = 1

                for _ in range(delay):
                    yield

                yield from wb_ctrl.slave_respond(resp_data, ack=ack, err=err, rty=rty)

                yield Settle()

        return f

    def _waiter(self):
        def f():
            while self.running:
                self.cycle_cnt += 1
                yield

        return f

    async def run(self, mem_model: CoreMemoryModel) -> bool:
        wb_instr_bus = WishboneBus(self.gp.wb_params)
        wb_data_bus = WishboneBus(self.gp.wb_params)
        core = Core(gen_params=self.gp, wb_instr_bus=wb_instr_bus, wb_data_bus=wb_data_bus)

        m = SimpleTestCircuit(core)

        wb_instr_ctrl = WishboneInterfaceWrapper(wb_instr_bus)
        wb_data_ctrl = WishboneInterfaceWrapper(wb_data_bus)

        self.running = True
        self.cycle_cnt = 0

        sim = PysimSimulator(m, traces_file=self.traces_file)
        sim.add_sync_process(self._wishbone_slave(mem_model, wb_instr_ctrl, is_instr_bus=True))
        sim.add_sync_process(self._wishbone_slave(mem_model, wb_data_ctrl, is_instr_bus=False))
        sim.add_sync_process(self._waiter())
        res = sim.run()

        if self.verbose:
            print(f"Simulation finished in {self.cycle_cnt} cycles")

        return res

    def stop(self):
        self.running = False
