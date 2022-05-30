from amaranth import Elaboratable, Module, C
from amaranth.sim import Passive

from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans

from .common import TestCaseWithSimulator, TestbenchIO

from coreblocks.another_reorder_buffer import ReorderBufferLayouts, ReorderBuffer

# TODO check if needed
from amaranth.sim import Simulator

class TestElaboratable(Elaboratable):
    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        with tm.transactionContext():
            self.layouts = ReorderBufferLayouts()
            self.rob = rob = ReorderBuffer(self.layouts)
            self.io_put = TestbenchIO(AdapterTrans(rob.put))
            self.io_discard = TestbenchIO(AdapterTrans(rob.discard))
            self.io_mark_done = TestbenchIO(AdapterTrans(rob.mark_done))

            m.submodules.rob = rob
            m.submodules.io_put = self.io_put
            m.submodules.io_discard = self.io_discard
            m.submodules.io_mark_done = self.io_mark_done

        return tm

# TODO basic properties:
# - after inserting ROB is not empty
#   - and therefore operations are ready
# - if you keep discarding and marking as done ROB will eventually be empty
# - you can discard as many entries as you've inserted and marked as done

class TestFillAndDumpRob(TestCaseWithSimulator):
    def dostuff(self):
        print("start?")
        for x in self.xs:
            i = yield from self.m.io_put.call({ 'entry_data': x })
            yield # TODO ^ doesn't wait for completion? or is the method buggy?
            s = yield self.m.rob.is_empty
            print(s)
            assert(not (yield self.m.rob.is_empty))
            assert(yield self.m.rob.mark_done.ready)
            yield from self.m.io_mark_done.call(i)
            yield

        print("done putting")
        for x in self.xs:
            print("discard")
            assert (yield self.m.rob.discard.is_ready)
            yield from self.m.io_discard.call()
            yield
            # TODO assert equal to x
        print("done?")
        assert(false) # TODO

    def test_single(self):
        self.m = m = TestElaboratable()
        size = 5 # TODO customize
        self.xs = [C(i) for i in range(5)]

        with self.runSimulation(m) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(self.dostuff)
