import random
from collections import deque
from typing import Dict, Callable, Any, Type

from amaranth import Elaboratable, Module

from coreblocks.params import GenParams
from coreblocks.transactions import TransactionModule
from coreblocks.transactions.lib import AdapterTrans
from test.common import TestbenchIO, TestCaseWithSimulator


class FunctionalTestCircuit(Elaboratable):
    """
    Common circuit for testing functional modules which are using @see{FuncUnitLayouts}.

    Parameters
    ----------
    gen: GenParams
        Core generation parameters.
    func_unit : Type
        Class of functional unit to be tested.
    """

    def __init__(self, gen: GenParams, func_unit: Type):
        self.gen = gen
        self.func_unit = func_unit

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        m.submodules.func_unit = func_unit = self.func_unit(self.gen)

        # mocked input and output
        m.submodules.issue_method = self.issue = TestbenchIO(AdapterTrans(func_unit.issue))
        m.submodules.accept_method = self.accept = TestbenchIO(AdapterTrans(func_unit.accept))

        return tm


class GenericFunctionalTestUnit(TestCaseWithSimulator):
    """
    Common test unit for testing functional modules which are using @see{FuncUnitLayouts}.
    For example of usage see @see{MultiplierUnitTest}.

    Parameters
    ----------
    operations: Dict[Any, Dict]
        List of operations performing by this unit.
    func_unit: Type
        Class of functional unit to be tested.
    expected: Callable[[int, int, Any, int], int]
        Function computing expected results
        (input_1, input_2, operation_key_from_operations, xlen) -> result.
    number_of_tests: int
        Number of random tests to be performed.
    seed: int
        Seed for generating random tests.
    gen: GenParams
        Core generation parameters.
    methodName: str
        Named test method to be executed. Necessary for Python to correctly run test.
    """

    def __init__(
        self,
        operations: Dict[Any, Dict],
        func_unit: Type,
        expected: Callable[[int, int, Any, int], int],
        number_of_tests: int = 2000,
        seed: int = 40,
        gen: GenParams = GenParams("rv32i"),
        method_name: str = "runTest",
    ):
        super().__init__(method_name)
        self.ops = operations
        self.func_unit = func_unit
        self.expected = expected
        self.number_of_tests = number_of_tests
        self.seed = seed
        self.gen = gen

    def setUp(self):
        self.m = FunctionalTestCircuit(self.gen, self.func_unit)

        random.seed(self.seed)
        self.requests = deque()
        self.responses = deque()

        max_int = 2**self.gen.isa.xlen - 1
        functions = list(self.ops.keys())

        for i in range(self.number_of_tests):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            mul_fn = functions[random.randint(0, len(functions) - 1)]
            rob_id = random.randint(0, 2**self.gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**self.gen.phys_regs_bits - 1)
            exec_fn = self.ops[mul_fn]
            result = self.expected(data1, data2, mul_fn, self.gen.isa.xlen)

            self.requests.append(
                {
                    "s1_val": data1,
                    "s2_val": 0 if data2_is_imm else data2,
                    "rob_id": rob_id,
                    "exec_fn": exec_fn,
                    "rp_dst": rp_dst,
                    "imm": data2 if data2_is_imm else 0,
                }
            )
            self.responses.append({"rob_id": rob_id, "result": result, "rp_dst": rp_dst})

    def run_pipeline(self):
        def random_wait():
            for i in range(random.randint(0, 10)):
                yield

        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                self.assertDictEqual(expected, result)
                yield from random_wait()

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                yield from random_wait()

        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(producer)
            sim.add_sync_process(consumer)
