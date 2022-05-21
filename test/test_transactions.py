from amaranth import *
from amaranth.sim import *

from .common import TestCaseWithSimulator

from coreblocks.transactions._utils import Scheduler


class TestScheduler(TestCaseWithSimulator):
    def count_test(self, sched, cnt):
        self.assertEqual(sched.count, cnt)
        self.assertEqual(len(sched.requests), cnt)
        self.assertEqual(len(sched.grant), cnt)
        self.assertEqual(len(sched.valid), 1)

    def sim_step(self, sched, request, expected_grant):
        yield sched.requests.eq(request)
        yield

        if request == 0:
            self.assertFalse((yield sched.valid))
        else:
            self.assertEqual((yield sched.grant), expected_grant)
            self.assertTrue((yield sched.valid))

    def test_single(self):
        sched = Scheduler(1)
        self.count_test(sched, 1)

        def process():
            yield from self.sim_step(sched, 0, 0)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 1, 1)
            yield from self.sim_step(sched, 0, 0)

        with self.runSimulation(sched) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)

    def test_multi(self):
        sched = Scheduler(4)
        self.count_test(sched, 4)

        def process():
            yield from self.sim_step(sched, 0b0000, 0b0000)
            yield from self.sim_step(sched, 0b1010, 0b0010)
            yield from self.sim_step(sched, 0b1010, 0b1000)
            yield from self.sim_step(sched, 0b1010, 0b0010)
            yield from self.sim_step(sched, 0b1001, 0b1000)
            yield from self.sim_step(sched, 0b1001, 0b0001)

            yield from self.sim_step(sched, 0b1111, 0b0010)
            yield from self.sim_step(sched, 0b1111, 0b0100)
            yield from self.sim_step(sched, 0b1111, 0b1000)
            yield from self.sim_step(sched, 0b1111, 0b0001)

            yield from self.sim_step(sched, 0b0000, 0b0000)
            yield from self.sim_step(sched, 0b0010, 0b0010)
            yield from self.sim_step(sched, 0b0010, 0b0010)

        with self.runSimulation(sched) as sim:
            sim.add_clock(1e-6)
            sim.add_sync_process(process)
