from amaranth.sim import Simulator
from cyclic_buffer import CyclicBuffer

dut = CyclicBuffer(10, 8)
def bench():
    yield dut.en.eq(0)
    assert True


sim = Simulator(dut)
sim.add_clock(1e-6) # 1 MHz
sim.add_sync_process(bench)
with sim.write_vcd("up_counter.vcd"):
    sim.run()
