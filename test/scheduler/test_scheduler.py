import random

from collections import namedtuple, deque
from typing import Callable, Optional, Iterable
from amaranth import *
from amaranth.sim import Settle
from parameterized import parameterized_class
from coreblocks.stages.rs_func_block import RSBlockComponent

from transactron.core import Method
from transactron.lib import FIFO, AdapterTrans, Adapter
from coreblocks.scheduler.scheduler import Scheduler
from coreblocks.structs_common.rf import RegisterFile
from coreblocks.structs_common.rat import FRAT
from coreblocks.params import RSLayouts, DecodeLayouts, SchedulerLayouts, GenParams, OpType, Funct3, Funct7
from coreblocks.params.configurations import test_core_config
from coreblocks.structs_common.rob import ReorderBuffer
from coreblocks.utils.protocols import FuncBlock
from ..common import RecordIntDict, TestCaseWithSimulator, TestGen, TestbenchIO, def_method_mock


class SchedulerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams, rs: list[set[OpType]]):
        self.gen_params = gen_params
        self.rs = rs

    def elaborate(self, platform):
        m = Module()

        rs_layouts = self.gen_params.get(RSLayouts, rs_entries_bits=self.gen_params.max_rs_entries_bits)
        decode_layouts = self.gen_params.get(DecodeLayouts)
        scheduler_layouts = self.gen_params.get(SchedulerLayouts)

        # data structures
        m.submodules.instr_fifo = instr_fifo = FIFO(decode_layouts.decoded_instr, 16)
        m.submodules.free_rf_fifo = free_rf_fifo = FIFO(
            scheduler_layouts.free_rf_layout, 2**self.gen_params.phys_regs_bits
        )
        m.submodules.rat = rat = FRAT(gen_params=self.gen_params)
        m.submodules.rob = self.rob = ReorderBuffer(self.gen_params)
        m.submodules.rf = self.rf = RegisterFile(gen_params=self.gen_params)

        # mocked RSFuncBlock
        class MockedRSFuncBlock(FuncBlock):
            def __init__(self, select, insert, clear):
                self.select = select
                self.insert = insert
                self.clear = clear

            update: Method
            get_result: Method

            def elaborate(self, platform):
                raise NotImplementedError

        method_rs_alloc = []
        method_rs_insert = []
        method_rs_clear = []
        rs_blocks: list[tuple[FuncBlock, set[OpType]]] = []
        self.rs_alloc = []
        self.rs_insert = []
        self.rs_clear = []

        # mocked RS
        for i, rs in enumerate(self.rs):
            alloc_adapter = Adapter(o=rs_layouts.select_out)
            insert_adapter = Adapter(i=rs_layouts.insert_in)
            clear_adapter = Adapter()

            select_test = TestbenchIO(alloc_adapter)
            insert_test = TestbenchIO(insert_adapter)
            clear_test = TestbenchIO(clear_adapter)

            method_rs_alloc.append(alloc_adapter)
            method_rs_insert.append(insert_adapter)
            method_rs_clear.append(clear_adapter)
            self.rs_alloc.append(select_test)
            self.rs_insert.append(insert_test)
            self.rs_clear.append(clear_test)
            rs_blocks.append((MockedRSFuncBlock(alloc_adapter.iface, insert_adapter.iface, clear_adapter.iface), rs))

            m.submodules[f"rs_alloc_{i}"] = self.rs_alloc[i]
            m.submodules[f"rs_insert_{i}"] = self.rs_insert[i]
            m.submodules[f"rs_clear_{i}"] = self.rs_clear[i]

        # mocked input and output
        m.submodules.rf_write = self.rf_write = TestbenchIO(AdapterTrans(self.rf.write))
        m.submodules.rf_free = self.rf_free = TestbenchIO(AdapterTrans(self.rf.free))
        m.submodules.rob_markdone = self.rob_done = TestbenchIO(AdapterTrans(self.rob.mark_done))
        m.submodules.rob_retire = self.rob_retire = TestbenchIO(AdapterTrans(self.rob.retire))
        m.submodules.instr_input = self.instr_inp = TestbenchIO(AdapterTrans(instr_fifo.write))
        m.submodules.free_rf_inp = self.free_rf_inp = TestbenchIO(AdapterTrans(free_rf_fifo.write))

        # main scheduler
        m.submodules.scheduler = self.scheduler = Scheduler(
            get_instr=instr_fifo.read,
            get_free_reg=free_rf_fifo.read,
            rat_rename=rat.rename,
            rob_put=self.rob.put,
            rf_read1=self.rf.read1,
            rf_read2=self.rf.read2,
            reservation_stations=rs_blocks,
            gen_params=self.gen_params,
        )

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

    def setUp(self):
        self.rs_count = len(self.optype_sets)
        self.gen_params = GenParams(
            test_core_config.replace(
                func_units_config=tuple(RSBlockComponent([], rs_entries=4) for _ in range(self.rs_count))
            )
        )
        self.expected_rename_queue = deque()
        self.expected_phys_reg_queue = deque()
        self.free_regs_queue = deque()
        self.free_ROB_entries_queue = deque()
        self.expected_rs_entry_queue = [deque() for _ in self.optype_sets]
        self.current_RAT = [0] * self.gen_params.isa.reg_cnt
        self.allocated_instr_count = 0
        self.m = SchedulerTestCircuit(self.gen_params, self.optype_sets)

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
        self.free_regs_queue.append({"reg_id": reg_id})
        self.expected_phys_reg_queue.append(reg_id)

    def queue_gather(self, queues: Iterable[deque]):
        # Iterate over all 'queues' and take one element from each, gathering
        # all key-value pairs into 'item'.
        item = {}
        for q in queues:
            partial_item = None
            # retry until we get an element
            while partial_item is None:
                # get element from one queue
                if q:
                    partial_item = q.popleft()
                    # None signals to end the process
                    if partial_item is None:
                        return None
                else:
                    # if no element available, wait and retry on the next clock cycle
                    yield

            # merge queue element with all previous ones (dict merge)
            item = item | partial_item
        return item

    def make_queue_process(
        self,
        *,
        io: TestbenchIO,
        input_queues: Optional[Iterable[deque]] = None,
        output_queues: Optional[Iterable[deque]] = None,
        check: Optional[Callable[[RecordIntDict, RecordIntDict], TestGen[None]]] = None,
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

        def queue_process():
            if always_enable:
                yield from io.enable()
            while True:
                inputs = {}
                outputs = {}
                # gather items from both queues
                if input_queues is not None:
                    inputs = yield from self.queue_gather(input_queues)
                if output_queues is not None:
                    outputs = yield from self.queue_gather(output_queues)

                # Check if queues signalled to end the process
                if inputs is None or outputs is None:
                    return

                result = yield from io.call(inputs)
                if always_enable:
                    yield from io.enable()

                # this could possibly be extended to automatically compare 'results' and
                # 'outputs' if check is None but that needs some dict deepcompare
                if check is not None:
                    yield Settle()
                    yield from check(result, outputs)

        if output_queues is None and input_queues is None:
            raise ValueError("Either output_queues or input_queues must be supplied")

        return queue_process

    def make_output_process(self, io: TestbenchIO, output_queues: Iterable[deque]):
        def check(got, expected):
            rl_dst = yield self.m.rob.data[got["rs_data"]["rob_id"]].rob_data.rl_dst
            s1 = self.rf_state[expected["rp_s1"]]
            s2 = self.rf_state[expected["rp_s2"]]

            # if source operand register ids are 0 then we already have values
            self.assertEqual(got["rs_data"]["rp_s1"], expected["rp_s1"] if not s1.valid else 0)
            self.assertEqual(got["rs_data"]["rp_s2"], expected["rp_s2"] if not s2.valid else 0)
            self.assertEqual(got["rs_data"]["rp_dst"], expected["rp_dst"])
            self.assertEqual(got["rs_data"]["exec_fn"], expected["exec_fn"])
            self.assertEqual(got["rs_entry_id"], expected["rs_entry_id"])
            self.assertEqual(got["rs_data"]["s1_val"], s1.value if s1.valid else 0)
            self.assertEqual(got["rs_data"]["s2_val"], s2.value if s2.valid else 0)
            self.assertEqual(rl_dst, expected["rl_dst"])

            # recycle physical register number
            if got["rs_data"]["rp_dst"] != 0:
                self.free_phys_reg(got["rs_data"]["rp_dst"])
            # recycle ROB entry
            self.free_ROB_entries_queue.append({"rob_id": got["rs_data"]["rob_id"]})

        return self.make_queue_process(io=io, output_queues=output_queues, check=check, always_enable=True)

    def test_randomized(self):
        def instr_input_process():
            yield from self.m.rob_retire.enable()

            # set up RF to reflect our static rf_state reference lookup table
            for i in range(2**self.gen_params.phys_regs_bits - 1):
                yield from self.m.rf_write.call(reg_id=i, reg_val=self.rf_state[i].value)
                if not self.rf_state[i].valid:
                    yield from self.m.rf_free.call(reg_id=i)

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

                yield from self.m.instr_inp.call(
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
                )
            # Terminate other processes
            self.expected_rename_queue.append(None)
            self.free_regs_queue.append(None)
            self.free_ROB_entries_queue.append(None)

        def rs_alloc_process(io: TestbenchIO, rs_id: int):
            @def_method_mock(lambda: io)
            def process():
                random_entry = random.randrange(self.gen_params.max_rs_entries)
                expected = self.expected_rename_queue.popleft()
                expected["rs_entry_id"] = random_entry
                self.expected_rs_entry_queue[rs_id].append(expected)

                # if last instruction was allocated stop simulation
                self.allocated_instr_count += 1
                if self.allocated_instr_count == self.instr_count:
                    for i in range(self.rs_count):
                        self.expected_rs_entry_queue[i].append(None)

                return {"rs_entry_id": random_entry}

            return process

        with self.run_simulation(self.m, max_cycles=1500) as sim:
            for i in range(self.rs_count):
                sim.add_sync_process(
                    self.make_output_process(io=self.m.rs_insert[i], output_queues=[self.expected_rs_entry_queue[i]])
                )
                sim.add_sync_process(rs_alloc_process(self.m.rs_alloc[i], i))
            sim.add_sync_process(
                self.make_queue_process(io=self.m.rob_done, input_queues=[self.free_ROB_entries_queue])
            )
            sim.add_sync_process(self.make_queue_process(io=self.m.free_rf_inp, input_queues=[self.free_regs_queue]))
            sim.add_sync_process(instr_input_process)
