from amaranth import *
from transactron.lib.sugar import MethodBrancher
from test.common import *
from transactron import *


class TestMethodBrancher(TestCaseWithSimulator):
    class Circuit(Elaboratable):
        def __init__(self, method: Method):
            self.method = method
            self.sig = Signal(2)
            self.out = Record(self.method.data_out.layout)

        def elaborate(self, platform):
            m = TModule()

            with Transaction().body(m):
                b = MethodBrancher(m, self.method)
                with m.If(self.sig == 0):
                    m.d.comb += self.out.eq(b(data=1))
                with m.If(self.sig == 1):
                    m.d.comb += self.out.eq(b(data=2))
            return m

    def setUp(self):
        random.seed(14)
        self.test_number = 15
        self.method_mock = MethodMock(i=data_layout(2), o=data_layout(4))
        self.circ = SimpleTestCircuit(self.Circuit(self.method_mock.get_method()))

        self.m = ModuleConnector(circ=self.circ, method_mock=self.method_mock)

    @def_method_mock(lambda self: self.method_mock)
    def mock_process(self, data):
        return {"data": data * 3}

    def process(self):
        for _ in range(self.test_number):
            input = random.randrange(3)
            yield self.circ._dut.sig.eq(input)
            yield
            data_out = yield self.circ._dut.out.data
            match input:
                case 0:
                    self.assertEqual(data_out, 3)
                case 1:
                    self.assertEqual(data_out, 6)
                case 2 | 3:
                    self.assertEqual(data_out, 0)

    def test_brancher(self):
        with self.run_simulation(self.m, 100) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.mock_process)
