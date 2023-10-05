from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_announcer import *


class TestVectorAnnouncer(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 30
        self.input_count = 3
        self.v_params = self.gen_params.v_params

        self.layout = FuncUnitLayouts(self.gen_params)

        self.circ = SimpleTestCircuit(VectorAnnouncer(self.gen_params, self.input_count))

        self.received = []
        self.send = []
        self.end = [False for _ in range(self.input_count + 1)]

    def generate_input(self):
        input = generate_instr(self.gen_params, self.layout.accept)
        input |= {"exception": random.randrange(2), "result": random.randrange(2**self.gen_params.isa.xlen)}
        return input

    def input_process(self, k):
        def f():
            for _ in range(self.test_number):
                input = self.generate_input()
                yield from self.circ.announce_list[k].call(input)
                self.send.append(input)
            self.end[k + 1] = True

        return f

    def accept_process(self):
        for _ in range(self.input_count * self.test_number):
            out = yield from self.circ.accept.call()
            self.received.append(out)
        self.end[0] = True

    def checker(self):
        while not all(self.end):
            yield
        self.assertEqual(len(self.send), len(self.received))
        for expected in self.send:
            self.received.remove(expected)
        self.assertEqual(len(self.received), 0)

    def test_random(self):
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.checker)
            sim.add_sync_process(self.accept_process)
            for k in range(self.input_count):
                sim.add_sync_process(self.input_process(k))
