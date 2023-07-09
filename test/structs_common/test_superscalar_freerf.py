from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from collections import deque
from parameterized import parameterized_class


@parameterized_class(["outputs_count"], [(1,), (2,), (3,), (4,), (5,)])
class TestSuperscalarFreeRF(TestCaseWithSimulator):
    outputs_count: int

    def setUp(self):
        random.seed(14)
        self.entries_count = 21
        self.test_cycles = 50

        self.circ = SimpleTestCircuit(SuperscalarFreeRF(self.entries_count, self.outputs_count))

        self.mirroring_freerf = {i for i in range(self.entries_count)}
        self.to_dealocate = deque()

        self.allocator_end = False
        self.deallocators_end = [False for i in range(self.outputs_count)]

    def allocator(self):
        for _ in range(self.test_cycles):
            reg_count = random.randrange(self.outputs_count) + 1
            regs = yield from self.circ.allocate.call(reg_count=reg_count)
            yield Settle()
            for i in range(reg_count):
                reg_id = regs[f"reg{i}"]
                self.assertIn(reg_id, self.mirroring_freerf)
                self.mirroring_freerf.remove(reg_id)
                self.to_dealocate.append(reg_id)
        self.allocator_end = True

    def dealocator(self, k: int):
        def f():
            while True:
                if not self.to_dealocate:
                    if self.allocator_end:
                        break
                    yield
                    continue
                reg_id = self.to_dealocate.popleft()
                yield from self.circ.deallocates[k].call(reg=reg_id)
                self.mirroring_freerf.add(reg_id)
            self.deallocators_end[k] = True

        return f

    def checker(self):
        while not (self.allocator_end and all(self.deallocators_end)):
            yield

        for i in range(self.entries_count):
            self.assertIn(i, self.mirroring_freerf)

    def test_random(self):
        with self.run_simulation(self.circ, 4000) as sim:
            sim.add_sync_process(self.checker)
            sim.add_sync_process(self.allocator)
            for i in range(self.outputs_count):
                sim.add_sync_process(self.dealocator(i))
