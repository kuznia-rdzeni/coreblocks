from dataclasses import asdict, dataclass
from itertools import product
import random
from collections import deque
from typing import Generic, TypeVar

from amaranth import Elaboratable, Module
from amaranth.sim import Passive

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.params.dependencies import DependencyManager
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.params.isa import Funct3, Funct7
from coreblocks.params.keys import ExceptionReportKey
from coreblocks.params.layouts import ExceptionRegisterLayouts
from coreblocks.params.optypes import OpType
from transactron.lib import AdapterTrans, Adapter
from test.common import RecordIntDict, RecordIntDictRet, TestbenchIO, TestCaseWithSimulator


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
        self.report_mock = TestbenchIO(Adapter(i=self.gen.get(ExceptionRegisterLayouts).report))
        self.gen.get(DependencyManager).add_dependency(ExceptionReportKey(), self.report_mock.adapter.iface)
        self.func_unit_comp = func_unit
        self.func_unit = self.func_unit_comp.get_module(self.gen)
        self.issue = TestbenchIO(AdapterTrans(self.func_unit.issue))
        self.accept = TestbenchIO(AdapterTrans(self.func_unit.accept))

    def elaborate(self, platform):
        m = Module()

        m.submodules.report_mock = self.report_mock

        m.submodules.func_unit = self.func_unit

        # mocked input and output
        m.submodules.issue_method = self.issue
        m.submodules.accept_method = self.accept

        return m


@dataclass
class ExecFn:
    op_type: OpType
    funct3: Funct3 = Funct3.ADD
    funct7: Funct7 = Funct7.ADD


_T = TypeVar("_T")


class FunctionalUnitTestCase(TestCaseWithSimulator, Generic[_T]):
    """
    Common test unit for testing functional modules which are using @see{FuncUnitLayouts}.
    For example of usage see @see{MultiplierUnitTest}.

    Attributes
    ----------
    operations: dict[_T, ExecFn]
        List of operations performed by this unit.
    func_unit: FunctionalComponentParams
        Unit parameters for the unit instantiated.
    number_of_tests: int
        Number of random tests to be performed per operation.
    seed: int
        Seed for generating random tests.
    zero_imm: bool
        Whether to set 'imm' to 0 or not in case 2nd operand comes from 's2_val'
    core_config: CoreConfiguration
        Core generation parameters.
    """

    ops: dict[_T, ExecFn]
    func_unit: FunctionalComponentParams
    number_of_tests = 50
    seed = 40
    zero_imm = True
    core_config = test_core_config

    @staticmethod
    def compute_result(i1: int, i2: int, i_imm: int, pc: int, fn: _T, xlen: int) -> dict[str, int]:
        """
        Computes expected results.

        Parameters
        ----------
        i1: int
            First argument value.
        i2: int
            Second argument value.
        i_imm: int
            Immediate value.
        pc: int
            Program counter value.
        fn: _T
            Function to execute.
        xlen: int
            Architecture bit width.
        """
        raise NotImplementedError

    def setUp(self):
        gen = GenParams(test_core_config)
        self.m = FunctionalTestCircuit(gen, self.func_unit)

        random.seed(self.seed)
        self.max_wait = 10
        self.requests = deque[RecordIntDict]()
        self.responses = deque[RecordIntDictRet]()
        self.exceptions = deque[RecordIntDictRet]()

        max_int = 2**gen.isa.xlen - 1
        functions = list(self.ops.keys())

        for op, _ in product(functions, range(self.number_of_tests)):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data_imm = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            rob_id = random.randint(0, 2**gen.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**gen.phys_regs_bits - 1)
            exec_fn = self.ops[op]
            pc = random.randint(0, max_int) & ~0b11
            results = self.compute_result(data1, data2, data_imm, pc, op, gen.isa.xlen)

            self.requests.append(
                {
                    "s1_val": data1,
                    "s2_val": 0 if data2_is_imm and self.zero_imm else data2,
                    "rob_id": rob_id,
                    "exec_fn": asdict(exec_fn),
                    "rp_dst": rp_dst,
                    "imm": data_imm if not self.zero_imm else data2 if data2_is_imm else 0,
                    "pc": pc,
                }
            )

            cause = None
            if "exception" in results:
                cause = results["exception"]
                results.pop("exception")

            self.responses.append({"rob_id": rob_id, "rp_dst": rp_dst, "exception": int(cause is not None)} | results)
            if cause is not None:
                self.exceptions.append({"rob_id": rob_id, "cause": cause})

    def random_wait(self):
        for i in range(random.randint(0, self.max_wait)):
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

        def exception_consumer():
            while self.exceptions:
                expected = self.exceptions.pop()
                result = yield from self.m.report_mock.call()
                self.assertDictEqual(expected, result)
                yield from self.random_wait()

            # keep partialy dependent tests from hanging up and detect extra calls
            yield Passive()
            result = yield from self.m.report_mock.call()
            self.assertFalse(True, "unexpected report call")

        return {
            "consumer": consumer,
            "producer": producer,
            "exception_consumer": exception_consumer,
        }

    def pipeline_verifier(self):
        yield Passive()
        while True:
            self.assertTrue((yield self.m.issue.adapter.iface.ready))
            self.assertEqual((yield self.m.issue.adapter.en), (yield self.m.issue.adapter.done))
            yield

    def run_standard_fu_test(self, pipeline_test=False):
        if pipeline_test:
            self.max_wait = 0

        procs = self.get_basic_processes()
        if pipeline_test:
            procs |= {"pipeline_verifier": self.pipeline_verifier}
        self.run_pipeline(self.get_basic_processes())

    def run_pipeline(self, custom_procs: dict):
        with self.run_simulation(self.m) as sim:
            for _, proc in custom_procs.items():
                sim.add_sync_process(proc)
