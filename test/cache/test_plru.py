import pytest

from transactron.testing import (
    TestCaseWithSimulator,
    SimpleTestCircuit,
    TestbenchContext,
)

from coreblocks.cache.plru import TreePLRU


class TestTreePLRU(TestCaseWithSimulator):
    def test_initial_victim_is_first_way(self):
        dut = SimpleTestCircuit(TreePLRU(4))

        async def proc(sim: TestbenchContext):
            assert (await dut.get_victim.call(sim))["way"] == 0

        with self.run_simulation(dut) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("ways", [2, 4, 8])
    def test_touched_way_is_not_the_victim(self, ways):
        dut = SimpleTestCircuit(TreePLRU(ways))

        async def proc(sim: TestbenchContext):
            # Whatever the accumulated state, touching a way must steer the victim
            # descent away from it, so it is never the immediate next victim
            for way in range(ways):
                await dut.touch[0].call(sim, way=way)
                assert (await dut.get_victim.call(sim))["way"] != way

        with self.run_simulation(dut) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("ways", [2, 4, 8])
    def test_touching_the_victim_cycles_all_ways(self, ways):
        dut = SimpleTestCircuit(TreePLRU(ways))

        async def proc(sim: TestbenchContext):
            # Repeatedly evicting and touching the victim must
            # visit every way exactly once before any way repeats
            seen = []
            for _ in range(ways):
                victim = (await dut.get_victim.call(sim))["way"]
                seen.append(victim)
                await dut.touch[0].call(sim, way=victim)

            assert sorted(seen) == list(range(ways))

            # After a full sweep the order repeats from the start
            assert (await dut.get_victim.call(sim))["way"] == seen[0]

        with self.run_simulation(dut) as sim:
            sim.add_testbench(proc)

    def test_lru_after_full_touch_sequence(self):
        dut = SimpleTestCircuit(TreePLRU(4))

        async def proc(sim: TestbenchContext):
            # Touch every way in order; the first-touched way is the pseudo-LRU
            for way in range(4):
                await dut.touch[0].call(sim, way=way)
            assert (await dut.get_victim.call(sim))["way"] == 0

        with self.run_simulation(dut) as sim:
            sim.add_testbench(proc)

    def test_higher_touch_port_wins(self):
        dut = SimpleTestCircuit(TreePLRU(2, touch_ports=2))

        async def proc(sim: TestbenchContext):
            # Both ports touch different ways in the same cycle. Port 1 (higher
            # index) wins on the shared node, so it protects way 0 and the victim
            # becomes way 1 - which is not what port 0 alone (touching way 1)
            # would produce, and differs from the untouched initial victim (0)
            dut.touch[0].call_init(sim, way=1)
            dut.touch[1].call_init(sim, way=0)
            await sim.tick()
            dut.touch[0].disable(sim)
            dut.touch[1].disable(sim)

            assert (await dut.get_victim.call(sim))["way"] == 1

        with self.run_simulation(dut) as sim:
            sim.add_testbench(proc)
