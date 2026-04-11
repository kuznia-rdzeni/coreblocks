from dataclasses import dataclass
import random
from amaranth import *

from collections import namedtuple, deque
from typing import Callable, Optional, Iterable
from parameterized import parameterized_class
from coreblocks.func_blocks.interface.func_protocols import FuncBlock
from coreblocks.interface.keys import CoreStateKey, RollbackKey
from coreblocks.interface.layouts import RSInterfaceLayouts, RetirementLayouts

from transactron.lib import FIFO, AdapterTrans, Adapter
from transactron.testing.functions import MethodData, data_const_to_dict
from transactron.testing.method_mock import MethodMock
from transactron.utils.amaranth_ext.elaboratables import ModuleConnector
from transactron.utils.dependencies import DependencyContext
from coreblocks.params.fu_params import BlockComponentParams
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.core_structs.rf import RegisterFile
from coreblocks.core_structs.crat import CheckpointRAT
from coreblocks.params import GenParams
from coreblocks.interface.layouts import RSLayouts, SchedulerLayouts
from coreblocks.arch import OpType, Funct3, Funct7
from coreblocks.params.configurations import test_core_config
from coreblocks.core_structs.rob import ReorderBuffer
from transactron.testing import TestCaseWithSimulator, TestbenchIO, def_method_mock, TestbenchContext


@dataclass(frozen=True)
class MockedBlockComponent(BlockComponentParams):
    op_types: set[OpType]
    rs_entries: int

    def get_module(self, gen_params: GenParams) -> FuncBlock:
        raise NotImplementedError()

    def get_optypes(self) -> set[OpType]:
        return self.op_types

    def get_layouts(self, gen_params: GenParams) -> RSInterfaceLayouts:
        return gen_params.get(RSLayouts, rs_entries=self.rs_entries).rs

    def get_rs_entry_count(self) -> int:
        return self.rs_entries


class SchedulerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()

        rs_layouts = self.gen_params.get(RSLayouts, rs_entries=self.gen_params.max_rs_entries)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)

        # data structures
        m.submodules.instr_fifo = instr_fifo = FIFO(scheduler_layouts.scheduler_in, 16)
        m.submodules.free_rf_fifo = free_rf_fifo = FIFO(
            scheduler_layouts.free_rf_layout, 2**self.gen_params.phys_regs_bits
        )
        m.submodules.crat = self.crat = crat = CheckpointRAT(gen_params=self.gen_params)
        m.submodules.rob = self.rob = ReorderBuffer(self.gen_params, 1)
        m.submodules.rf = self.rf = RegisterFile(gen_params=self.gen_params, read_ports=2, write_ports=1, free_ports=1)

        self.rs_alloc: list[TestbenchIO] = []
        self.rs_insert: list[TestbenchIO] = []

        # mocked RS
        for i in range(len(self.gen_params.func_units_config)):
            select_test = TestbenchIO(Adapter(o=rs_layouts.rs.select_out))
            insert_test = TestbenchIO(Adapter(i=rs_layouts.rs.insert_in))

            self.rs_alloc.append(select_test)
            self.rs_insert.append(insert_test)

            m.submodules[f"rs_alloc_{i}"] = self.rs_alloc[i]
            m.submodules[f"rs_insert_{i}"] = self.rs_insert[i]

        # mocked input and output
        m.submodules.rf_write = self.rf_write = TestbenchIO(AdapterTrans.create(self.rf.write[0]))
        m.submodules.rf_free = self.rf_free = TestbenchIO(AdapterTrans.create(self.rf.free[0]))
        m.submodules.rob_markdone = self.rob_done = TestbenchIO(AdapterTrans.create(self.rob.mark_done[0]))
        m.submodules.rob_retire = self.rob_retire = TestbenchIO(AdapterTrans.create(self.rob.retire))
        m.submodules.rob_peek = self.rob_peek = TestbenchIO(AdapterTrans.create(self.rob.peek))
        m.submodules.rob_get_indices = self.rob_get_indices = TestbenchIO(AdapterTrans.create(self.rob.get_indices))
        m.submodules.instr_input = self.instr_inp = TestbenchIO(AdapterTrans.create(instr_fifo.write))
        m.submodules.free_rf_inp = self.free_rf_inp = TestbenchIO(AdapterTrans.create(free_rf_fifo.write))
        m.submodules.core_state = self.core_state = TestbenchIO(
            Adapter(o=self.gen_params.get(RetirementLayouts).core_state)
        )
        m.submodules.get_active_tags = self.get_active_tags = TestbenchIO(AdapterTrans.create(crat.get_active_tags))
        m.submodules.free_tag = self.free_tag = TestbenchIO(AdapterTrans.create(crat.free_tag))
        dm = DependencyContext.get()
        dm.add_dependency(CoreStateKey(), self.core_state.adapter.iface)

        # main scheduler
        m.submodules.scheduler = self.scheduler = Scheduler(gen_params=self.gen_params)
        self.scheduler.get_instr.provide(instr_fifo.read)
        self.scheduler.get_free_reg[0].provide(free_rf_fifo.read)
        self.scheduler.crat_rename.provide(crat.rename)
        self.scheduler.crat_tag.provide(crat.tag)
        self.scheduler.crat_active_tags.provide(crat.get_active_tags)
        self.scheduler.rob_put.provide(self.rob.put)
        self.scheduler.rf_read_req1.provide(self.rf.read_req[0])
        self.scheduler.rf_read_req2.provide(self.rf.read_req[1])
        self.scheduler.rf_read_resp1.provide(self.rf.read_resp[0])
        self.scheduler.rf_read_resp2.provide(self.rf.read_resp[1])
        for i, (rs_select, rs_insert) in enumerate(zip(self.rs_alloc, self.rs_insert)):
            self.scheduler.rs_select[i].provide(rs_select.adapter.iface)
            self.scheduler.rs_insert[i].provide(rs_insert.adapter.iface)

        rollback, rollback_unifiers = dm.get_dependency(RollbackKey())
        m.submodules.rollback_unifiers = ModuleConnector(**rollback_unifiers)
        m.submodules.rollback = self.rollback = TestbenchIO(AdapterTrans.create(rollback))

        return m


@parameterized_class(
    ("name", "optype_sets", "instr_count"),
    [
        ("One-RS", [set(OpType)], 100),
        ("Two-RS", [{OpType.ARITHMETIC, OpType.COMPARE}, {OpType.MUL, OpType.COMPARE}], 500),
        (
            "Three-RS",
            [{OpType.ARITHMETIC, OpType.COMPARE}, {OpType.MUL, OpType.COMPARE}, {OpType.DIV_REM, OpType.COMPARE}],
            300,
        ),
    ],
)
class TestScheduler(TestCaseWithSimulator):
    optype_sets: list[set[OpType]]
    instr_count: int

    def setup_method(self):
        self.rs_count = len(self.optype_sets)
        self.gen_params = GenParams(
            test_core_config.replace(
                func_units_config=tuple(MockedBlockComponent(optypes, rs_entries=4) for optypes in self.optype_sets),
                allow_partial_extensions=True,
            )
        )
        self.expected_rename_queue = deque()
        self.expected_phys_reg_queue = deque()
        self.free_regs_queue = deque()
        self.free_ROB_entries_queue = deque()
        self.expected_rs_entry_queue = [deque() for _ in self.optype_sets]
        self.current_RAT = [0] * self.gen_params.isa.reg_cnt
        self.allocated_instr_count = 0
        self.m = SchedulerTestCircuit(self.gen_params)

        random.seed(42)

        # set up static RF state lookup table
        RFEntry = namedtuple("RFEntry", ["value", "valid"])
        self.rf_state = [
            RFEntry(random.randrange(self.gen_params.isa.xlen), random.randrange(2))
            for _ in range(2**self.gen_params.phys_regs_bits)
        ]
        self.rf_state[0] = RFEntry(0, 1)

        for i in range(1, 2**self.gen_params.phys_regs_bits):
            self.free_phys_reg(i)

    def free_phys_reg(self, reg_id):
        self.free_regs_queue.append({"ident": reg_id})
        self.expected_phys_reg_queue.append(reg_id)

    async def queue_gather(self, sim: TestbenchContext, queues: Iterable[deque]):
        # Iterate over all 'queues' and take one element from each, gathering
        # all key-value pairs into 'item'.
        item = {}
        for q in queues:
            partial_item = None
            # retry until we get an element
            while partial_item is None:
                # get element from one queue
                await sim.delay(1e-9)
                if q:
                    partial_item = q.popleft()
                    # None signals to end the process
                    if partial_item is None:
                        return None
                else:
                    # if no element available, wait and retry on the next clock cycle
                    await sim.tick()

            # merge queue element with all previous ones (dict merge)
            item = item | partial_item
        return item

    def make_queue_process(
        self,
        *,
        io: TestbenchIO,
        input_queues: Optional[Iterable[deque]] = None,
        output_queues: Optional[Iterable[deque]] = None,
        check: Optional[Callable[[TestbenchContext, MethodData, dict], None]] = None,
        always_enable: bool = False,
    ):
        """Create queue gather-and-test process

        This function returns a simulation process that does the following steps:
        1. Gathers dicts from multiple `queues` (one dict from each) and joins
           them together (items from queues are popped using popleft)
        2. `io` is called with items gathered from `input_queues`
        3. If `check` was supplied, it's called with the results returned from
           call in step 2. and items gathered from `output_queues`
        Steps 1-3 are repeated until one of the queues receives None

        Intention is to simplify writing tests with queues: `input_queues` lets
        the user specify multiple data sources (queues) from which to gather
        arguments for call to `io`, and multiple data sources (queues) from which
        to gather reference values to test against the results from the call to `io`.

        Parameters
        ----------
        io : TestbenchIO
            TestbenchIO to call with items gathered from `input_queues`.
        input_queues : deque[dict], optional
            Queue of dictionaries containing fields and values of a record to call
            `io` with. Different fields may be split across multiple queues.
            Fields with the same name in different queues must not be used.
            Dictionaries are popped from the deques using popleft.
        output_queues : deque[dict], optional
            Queue of dictionaries containing reference fields and values to compare
            results of `io` call with. Different fields may be split across
            multiple queues. Fields with the same name in different queues must
            not be used. Dictionaries are popped from the deques using popleft.
        check : Callable[[dict, dict], TestGen]
            Testbench generator which will be called with parameters `result`
            and `outputs`, meaning results from the call to `io` and item
            gathered from `output_queues`.
        always_enable: bool
            Makes `io` method always appear enabled.

        Returns
        -------
        Callable[None, TestGen]
            Simulation process performing steps described above.

        Raises
        ------
        ValueError
            If neither `input_queues` nor `output_queues` are supplied.
        """

        async def queue_process(sim: TestbenchContext):
            if always_enable:
                io.enable(sim)
            while True:
                inputs = {}
                outputs = {}
                # gather items from both queues
                if input_queues is not None:
                    inputs = await self.queue_gather(sim, input_queues)
                if output_queues is not None:
                    outputs = await self.queue_gather(sim, output_queues)

                # Check if queues signalled to end the process
                if inputs is None or outputs is None:
                    return

                result = await io.call(sim, inputs)
                if always_enable:
                    io.enable(sim)

                # this could possibly be extended to automatically compare 'results' and
                # 'outputs' if check is None but that needs some dict deepcompare
                if check is not None:
                    check(sim, result, outputs)

        if output_queues is None and input_queues is None:
            raise ValueError("Either output_queues or input_queues must be supplied")

        return queue_process

    def make_output_process(self, io: TestbenchIO, output_queues: Iterable[deque]):
        def check(sim: TestbenchContext, got: MethodData, expected: dict):
            # TODO: better stubs for Memory?
            rl_dst = sim.get(self.m.rob.data.data[got.rs_data.rob_id].rl_dst)  # type: ignore
            s1 = self.rf_state[expected["rp_s1"]]
            s2 = self.rf_state[expected["rp_s2"]]

            # if source operand register ids are 0 then we already have values
            assert got.rs_data.rp_s1 == (expected["rp_s1"] if not s1.valid else 0)
            assert got.rs_data.rp_s2 == (expected["rp_s2"] if not s2.valid else 0)
            assert got.rs_data.rp_dst == expected["rp_dst"]
            assert data_const_to_dict(got.rs_data.exec_fn) == expected["exec_fn"]
            assert got.rs_entry_id == expected["rs_entry_id"]
            assert got.rs_data.s1_val == (s1.value if s1.valid else 0)
            assert got.rs_data.s2_val == (s2.value if s2.valid else 0)
            assert rl_dst == expected["rl_dst"]

            # recycle physical register number
            if got.rs_data.rp_dst != 0:
                self.free_phys_reg(got.rs_data.rp_dst)
            # recycle ROB entry
            self.free_ROB_entries_queue.append({"rob_id": got.rs_data.rob_id})

        return self.make_queue_process(io=io, output_queues=output_queues, check=check, always_enable=True)

    def test_randomized(self):
        async def instr_input_process(sim: TestbenchContext):
            self.m.rob_retire.enable(sim)
            self.m.rob_retire.set_inputs(sim, {"count": 1})

            # set up RF to reflect our static rf_state reference lookup table
            for i in range(2**self.gen_params.phys_regs_bits - 1):
                await self.m.rf_write.call(sim, reg_id=i, reg_val=self.rf_state[i].value)
                if not self.rf_state[i].valid:
                    await self.m.rf_free.call(sim, reg_id=i)

            op_types_set = set()
            for rs in self.optype_sets:
                op_types_set = op_types_set.union(rs)

            for i in range(self.instr_count):
                rl_s1 = random.randrange(self.gen_params.isa.reg_cnt)
                rl_s2 = random.randrange(self.gen_params.isa.reg_cnt)
                rl_dst = random.randrange(self.gen_params.isa.reg_cnt)

                op_type = random.choice(list(op_types_set))
                funct3 = random.choice(list(Funct3))
                funct7 = random.choice(list(Funct7))
                immediate = random.randrange(2**32)
                rp_s1 = self.current_RAT[rl_s1]
                rp_s2 = self.current_RAT[rl_s2]
                rp_dst = self.expected_phys_reg_queue.popleft() if rl_dst != 0 else 0

                self.expected_rename_queue.append(
                    {
                        "rp_s1": rp_s1,
                        "rp_s2": rp_s2,
                        "rl_dst": rl_dst,
                        "rp_dst": rp_dst,
                        "exec_fn": {
                            "op_type": op_type,
                            "funct3": funct3,
                            "funct7": funct7,
                        },
                    }
                )
                self.current_RAT[rl_dst] = rp_dst

                await self.m.instr_inp.call(
                    sim,
                    count=1,
                    data=[
                        {
                            "exec_fn": {
                                "op_type": op_type,
                                "funct3": funct3,
                                "funct7": funct7,
                            },
                            "regs_l": {
                                "rl_s1": rl_s1,
                                "rl_s2": rl_s2,
                                "rl_dst": rl_dst,
                            },
                            "imm": immediate,
                        }
                    ],
                )
            # Terminate other processes
            self.expected_rename_queue.append(None)
            self.free_regs_queue.append(None)
            self.free_ROB_entries_queue.append(None)

        def rs_alloc_process(io: TestbenchIO, rs_id: int):
            @def_method_mock(lambda: io)
            def process():
                random_entry = random.randrange(self.gen_params.max_rs_entries)

                @MethodMock.effect
                def eff():
                    expected = self.expected_rename_queue.popleft()
                    expected["rs_entry_id"] = random_entry
                    self.expected_rs_entry_queue[rs_id].append(expected)

                    # if last instruction was allocated stop simulation
                    self.allocated_instr_count += 1
                    if self.allocated_instr_count == self.instr_count:
                        for i in range(self.rs_count):
                            self.expected_rs_entry_queue[i].append(None)

                return {"rs_entry_id": random_entry}

            return process()

        @def_method_mock(lambda: self.m.core_state)
        def core_state_mock():
            # TODO: flushing test
            return {"flushing": 0}

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            for i in range(self.rs_count):
                sim.add_testbench(
                    self.make_output_process(io=self.m.rs_insert[i], output_queues=[self.expected_rs_entry_queue[i]])
                )
                self.add_mock(sim, rs_alloc_process(self.m.rs_alloc[i], i))
            sim.add_testbench(self.make_queue_process(io=self.m.rob_done, input_queues=[self.free_ROB_entries_queue]))
            sim.add_testbench(self.make_queue_process(io=self.m.free_rf_inp, input_queues=[self.free_regs_queue]))
            sim.add_testbench(instr_input_process)
