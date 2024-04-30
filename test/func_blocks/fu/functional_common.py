from dataclasses import asdict, dataclass
from itertools import product
import random
import pytest
from collections import deque
from typing import Generic, TypeVar

from amaranth import Elaboratable, Signal
from amaranth.sim import Passive

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.arch import Funct3, Funct7
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, ExceptionReportKey
from coreblocks.interface.layouts import ExceptionRegisterLayouts
from coreblocks.arch.optypes import OpType
from transactron.lib import Adapter
from transactron.testing import RecordIntDict, RecordIntDictRet, TestbenchIO, TestCaseWithSimulator, SimpleTestCircuit
from transactron.utils import ModuleConnector


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

    @pytest.fixture(autouse=True)
    def setup(self, configure_dependency_context):
        self.gen_params = GenParams(test_core_config)

        self.report_mock = TestbenchIO(Adapter(i=self.gen_params.get(ExceptionRegisterLayouts).report))

        DependencyContext.get().add_dependency(ExceptionReportKey(), self.report_mock.adapter.iface)
        DependencyContext.get().add_dependency(AsyncInterruptInsertSignalKey(), Signal())

        self.m = SimpleTestCircuit(self.func_unit.get_module(self.gen_params))
        self.circ = ModuleConnector(dut=self.m, report_mock=self.report_mock)

        random.seed(self.seed)
        self.requests = deque[RecordIntDict]()
        self.responses = deque[RecordIntDictRet]()
        self.exceptions = deque[RecordIntDictRet]()

        max_int = 2**self.gen_params.isa.xlen - 1
        functions = list(self.ops.keys())

        for op, _ in product(functions, range(self.number_of_tests)):
            data1 = random.randint(0, max_int)
            data2 = random.randint(0, max_int)
            data_imm = random.randint(0, max_int)
            data2_is_imm = random.randint(0, 1)
            rob_id = random.randint(0, 2**self.gen_params.rob_entries_bits - 1)
            rp_dst = random.randint(0, 2**self.gen_params.phys_regs_bits - 1)
            exec_fn = self.ops[op]
            pc = random.randint(0, max_int) & ~0b11
            results = self.compute_result(data1, data2, data_imm, pc, op, self.gen_params.isa.xlen)

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
                self.exceptions.append({"rob_id": rob_id, "cause": cause, "pc": results.setdefault("exception_pc", pc)})

                results.pop("exception")
                results.pop("exception_pc")

            self.responses.append({"rob_id": rob_id, "rp_dst": rp_dst, "exception": int(cause is not None)} | results)

    def consumer(self):
        while self.responses:
            expected = self.responses.pop()
            result = yield from self.m.accept.call()
            assert expected == result
            yield from self.random_wait(self.max_wait)

    def producer(self):
        while self.requests:
            req = self.requests.pop()
            yield from self.m.issue.call(req)
            yield from self.random_wait(self.max_wait)

    def exception_consumer(self):
        while self.exceptions:
            expected = self.exceptions.pop()
            result = yield from self.report_mock.call()
            assert expected == result
            yield from self.random_wait(self.max_wait)

        # keep partialy dependent tests from hanging up and detect extra calls
        yield Passive()
        result = yield from self.report_mock.call()
        assert not True, "unexpected report call"

    def pipeline_verifier(self):
        yield Passive()
        while True:
            assert (yield self.m.issue.adapter.iface.ready)
            assert (yield self.m.issue.adapter.en) == (yield self.m.issue.adapter.done)
            yield

    def run_standard_fu_test(self, pipeline_test=False):
        if pipeline_test:
            self.max_wait = 0
        else:
            self.max_wait = 10

        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.producer)
            sim.add_sync_process(self.consumer)
            sim.add_sync_process(self.exception_consumer)
            if pipeline_test:
                sim.add_sync_process(self.pipeline_verifier)
