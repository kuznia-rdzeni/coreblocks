from dataclasses import asdict, dataclass
from itertools import product
import random
import pytest
from collections import deque
from typing import Generic, TypeVar

from amaranth import Elaboratable, Signal

from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from coreblocks.priv.csr.csr_instances import GenericCSRRegisters
from transactron.testing.functions import data_const_to_dict
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.fu_params import FunctionalComponentParams
from coreblocks.arch import Funct3, Funct7
from coreblocks.interface.keys import AsyncInterruptInsertSignalKey, ExceptionReportKey, CSRInstancesKey
from coreblocks.interface.layouts import ExceptionRegisterLayouts
from coreblocks.arch.optypes import OpType
from transactron.lib import Adapter
from transactron.testing import (
    RecordIntDict,
    TestbenchIO,
    TestCaseWithSimulator,
    SimpleTestCircuit,
    ProcessContext,
    TestbenchContext,
)
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
    def setup(self, fixture_initialize_testing_env):
        self.gen_params = GenParams(test_core_config)

        self.report_mock = TestbenchIO(Adapter.create(i=self.gen_params.get(ExceptionRegisterLayouts).report))
        self.csrs = GenericCSRRegisters(self.gen_params)

        DependencyContext.get().add_dependency(ExceptionReportKey(), self.report_mock.adapter.iface)
        DependencyContext.get().add_dependency(AsyncInterruptInsertSignalKey(), Signal())
        DependencyContext.get().add_dependency(CSRInstancesKey(), self.csrs)

        self.m = SimpleTestCircuit(self.func_unit.get_module(self.gen_params))
        self.circ = ModuleConnector(dut=self.m, report_mock=self.report_mock, csrs=self.csrs)

        random.seed(self.seed)
        self.requests = deque[RecordIntDict]()
        self.responses = deque[RecordIntDict]()
        self.exceptions = deque[RecordIntDict]()

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
                self.exceptions.append(
                    {
                        "rob_id": rob_id,
                        "cause": cause,
                        "pc": results.setdefault("exception_pc", pc),
                        "mtval": results.setdefault("mtval", 0),
                    }
                )

                results.pop("exception")
                results.pop("exception_pc")
                results.pop("mtval")

            self.responses.append({"rob_id": rob_id, "rp_dst": rp_dst, "exception": int(cause is not None)} | results)

    async def consumer(self, sim: TestbenchContext):
        while self.responses:
            expected = self.responses.pop()
            result = await self.m.push_result.call(sim)
            assert expected == data_const_to_dict(result)
            await self.random_wait(sim, self.max_wait)

    async def producer(self, sim: TestbenchContext):
        while self.requests:
            req = self.requests.pop()
            await self.m.issue.call(sim, req)
            await self.random_wait(sim, self.max_wait)

    async def exception_consumer(self, sim: TestbenchContext):
        # This is a background testbench so that extra calls can be detected reliably
        with sim.critical():
            while self.exceptions:
                expected = self.exceptions.pop()
                result = await self.report_mock.call(sim)
                assert expected == data_const_to_dict(result)
                await self.random_wait(sim, self.max_wait)

        # keep partialy dependent tests from hanging up and detect extra calls
        result = await self.report_mock.call(sim)
        assert not True, "unexpected report call"

    async def pipeline_verifier(self, sim: ProcessContext):
        async for *_, ready, en, done in sim.tick().sample(
            self.m.issue.adapter.iface.ready, self.m.issue.adapter.en, self.m.issue.adapter.done
        ):
            assert ready
            assert en == done

    def run_standard_fu_test(self, pipeline_test=False):
        if pipeline_test:
            self.max_wait = 0
        else:
            self.max_wait = 10

        with self.run_simulation(self.circ) as sim:
            sim.add_testbench(self.producer)
            sim.add_testbench(self.consumer)
            sim.add_testbench(self.exception_consumer, background=True)
            if pipeline_test:
                sim.add_process(self.pipeline_verifier)
