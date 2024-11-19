import random
from amaranth import *
from amaranth.sim import *

from transactron.testing import TestCaseWithSimulator, TestbenchIO, data_layout, TestbenchContext

from transactron import *
from transactron.testing.method_mock import def_method_mock
from transactron.lib import *
from transactron.testing.testbenchio import CallTrigger


class ValidateArgumentsTestCircuit(Elaboratable):
    def elaborate(self, platform):
        m = Module()

        self.method = TestbenchIO(Adapter(i=data_layout(1), o=data_layout(1)).set(with_validate_arguments=True))
        self.caller1 = TestbenchIO(AdapterTrans(self.method.adapter.iface))
        self.caller2 = TestbenchIO(AdapterTrans(self.method.adapter.iface))

        m.submodules += [self.method, self.caller1, self.caller2]

        return m


class TestValidateArguments(TestCaseWithSimulator):
    def control_caller(self, caller: TestbenchIO, method: TestbenchIO):
        async def process(sim: TestbenchContext):
            await sim.tick()
            for _ in range(100):
                val = random.randrange(2)
                pre_accepted_val = self.accepted_val
                caller_data, method_data = await CallTrigger(sim).call(caller, data=val).sample(method)
                if caller_data is not None:
                    assert val == pre_accepted_val
                    assert caller_data.data == val
                else:
                    assert val != pre_accepted_val or val == pre_accepted_val and method_data is not None

        return process

    def validate_arguments(self, data: int):
        return data == self.accepted_val

    async def changer(self, sim: TestbenchContext):
        for _ in range(50):
            await sim.tick()
        self.accepted_val = 1

    @def_method_mock(tb_getter=lambda self: self.m.method, validate_arguments=validate_arguments)
    def method_mock(self, data: int):
        return {"data": data}

    def test_validate_arguments(self):
        random.seed(42)
        self.m = ValidateArgumentsTestCircuit()
        self.accepted_val = 0
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.changer)
            sim.add_testbench(self.control_caller(self.m.caller1, self.m.method))
            sim.add_testbench(self.control_caller(self.m.caller2, self.m.method))
