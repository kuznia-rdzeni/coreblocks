import random
from collections import deque
from typing import Dict, Callable, Any, Optional

from amaranth import Elaboratable, Module

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.transactions.lib import AdapterTrans
from test.common import TestbenchIO, TestCaseWithSimulator


class FunctionalTestCircuit(Elaboratable):
    """
    Common circuit for testing functional modules which are using @see{FuncUnitLayouts}.

    Parameters
    ----------
    gen: GenParams
        Core generation parameters.
    func_unit : FunctionalComponentParams
        Class of functional unit to be tested.
    """

    def __init__(self, gen: GenParams, func_unit: FunctionalComponentParams):
        self.gen = gen
        self.func_unit_comp = func_unit
        self.func_unit = self.func_unit_comp.get_module(self.gen)
        self.issue = TestbenchIO(AdapterTrans(self.func_unit.issue))
        self.accept = TestbenchIO(AdapterTrans(self.func_unit.accept))

    def elaborate(self, platform):
        m = Module()

        m.submodules.func_unit = self.func_unit

        # mocked input and output
        m.submodules.issue_method = self.issue
        m.submodules.accept_method = self.accept

        return m


class GenericFunctionalTestUnit(TestCaseWithSimulator):
    """
    Common test unit for testing functional modules which are using @see{FuncUnitLayouts}.
    For example of usage see @see{MultiplierUnitTest}.

    Parameters
    ----------
    operations: Dict[Any, Dict]
        List of operations performed by this unit.
    func_unit: FunctionalComponentParams
        Class of functional unit to be tested.
    expected: Callable[[int, int, int, int, Any, int], Dict[str, int]]
        Function computing expected results
        (input_1, input_2, input_imm, pc, operation_key_from_operations, xlen) -> results dict.
    number_of_tests: int
        Number of random tests to be performed.
    seed: int
        Seed for generating random tests.
    zero_imm: bool
        Whether to set 'imm' to 0 or not in case 2nd operand comes from 's2_val'
    gen: GenParams
        Core generation parameters.
    methodName: str
        Named test method to be executed. Necessary for Python to correctly run test.
    """

    def __init__(
        self,
        operations: Dict[Any, Dict],
        func_unit: FunctionalComponentParams,
        expected: Callable[[int, int, int, int, Any, int], Dict[str, int]],
        number_of_tests: int = 2000,
        seed: int = 40,
        zero_imm: bool = True,
        gen: GenParams = GenParams(test_core_config),
        method_name: str = "runTest",
    ):
        super().__init__(method_name)
        self.ops = operations
        self.func_unit = func_unit
        self.expected = expected
        self.number_of_tests = number_of_tests
        self.seed = seed
        self.zero_imm = zero_imm
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
            data_imm = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            op = random.choice(functions)
            rob_id = random.randint(0, 2**self.gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**self.gen.phys_regs_bits - 1)
            exec_fn = self.ops[op]
            pc = random.randint(0, max_int) & ~0b11
            results = self.expected(data1, data2, data_imm, pc, op, self.gen.isa.xlen)

            self.requests.append(
                {
                    "s1_val": data1,
                    "s2_val": 0 if data2_is_imm and self.zero_imm else data2,
                    "rob_id": rob_id,
                    "exec_fn": exec_fn,
                    "rp_dst": rp_dst,
                    "imm": data_imm if not self.zero_imm else data2 if data2_is_imm else 0,
                    "pc": pc,
                }
            )
            self.responses.append({"rob_id": rob_id, "rp_dst": rp_dst} | results)

    def random_wait(self):
        for i in range(random.randint(0, 10)):
            yield

    def get_basic_processes(self):
        def consumer():
            while self.responses:
                expected = self.responses.pop()
                result = yield from self.m.accept.call()
                self.assertDictEqual(expected, result)
                yield from self.random_wait()

        def producer():
            while self.requests:
                req = self.requests.pop()
                yield from self.m.issue.call(req)
                yield from self.random_wait()

        return {
            "consumer": consumer,
            "producer": producer,
        }

    def run_pipeline(self, custom_procs: Optional[Dict] = None):
        if custom_procs is not None:
            procs = custom_procs
        else:
            procs = self.get_basic_processes()

        with self.run_simulation(self.m) as sim:
            for _, proc in procs.items():
                sim.add_sync_process(proc)
