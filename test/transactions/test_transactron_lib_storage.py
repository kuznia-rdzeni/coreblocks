from transactron.testing import *
import random
from transactron.lib.storage import ContentAddressableMemory


class TestContentAddressableMemory(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.test_number = 50
        self.addr_width = 4
        self.content_width = 5
        self.entries_count = 8
        self.addr_layout = data_layout(self.addr_width)
        self.content_layout = data_layout(self.content_width)

        self.circ = SimpleTestCircuit(
            ContentAddressableMemory(self.addr_layout, self.content_layout, self.entries_count)
        )

        self.memory = {}

    def input_process(self):
        for _ in range(self.test_number):
            while True:
                addr = generate_based_on_layout(self.addr_layout)
                frozen_addr = frozenset(addr.items())
                if frozen_addr not in self.memory:
                    break
            content = generate_based_on_layout(self.content_layout)
            yield from self.circ.push.call(addr=addr, data=content)
            yield Settle()
            self.memory[frozen_addr] = content

    def output_process(self):
        yield Passive()
        while True:
            addr = generate_based_on_layout(self.addr_layout)
            res = yield from self.circ.pop.call(addr=addr)
            frozen_addr = frozenset(addr.items())
            if frozen_addr in self.memory:
                self.assertEqual(res["not_found"], 0)
                self.assertEqual(res["data"], self.memory[frozen_addr])
                self.memory.pop(frozen_addr)
            else:
                self.assertEqual(res["not_found"], 1)

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.input_process)
            sim.add_sync_process(self.output_process)
