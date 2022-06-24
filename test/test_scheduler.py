import random
import queue
from collections import namedtuple
from typing import Callable, Optional, Iterable
from amaranth import *
from amaranth.back import verilog
from amaranth.sim import Simulator, Settle
from coreblocks.transactions import TransactionModule, TransactionContext
from coreblocks.transactions.lib import FIFO, ConnectTrans, AdapterTrans, Adapter
from coreblocks.scheduler import Scheduler
from coreblocks.rf import RegisterFile
from coreblocks.rat import FRAT
from coreblocks.layouts import SchedulerLayouts, RSLayouts
from coreblocks.genparams import GenParams
from coreblocks.reorder_buffer import ReorderBuffer
from .common import RecordIntDict, TestCaseWithSimulator, TestGen, TestbenchIO


class SchedulerTestCircuit(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params

    def elaborate(self, platform):
        m = Module()
        tm = TransactionModule(m)

        layouts = self.gen_params.get(SchedulerLayouts)
        rs_layouts = self.gen_params.get(RSLayouts)

        with tm.transactionContext():
            # data structures
            m.submodules.instr_fifo = instr_fifo = FIFO(layouts.instr_layout, 16)
            m.submodules.free_rf_fifo = free_rf_fifo = FIFO(
                self.gen_params.phys_regs_bits, 2**self.gen_params.phys_regs_bits
            )
            m.submodules.rat = rat = FRAT(gen_params=self.gen_params)
            m.submodules.rob = self.rob = ReorderBuffer(self.gen_params)
            m.submodules.rf = self.rf = RegisterFile(gen_params=self.gen_params)

            # mocked RS
            method_rs_alloc = Adapter(i=rs_layouts.rs_allocate_out, o=rs_layouts.rs_allocate_out)
            method_rs_insert = Adapter(i=rs_layouts.rs_insert_in, o=rs_layouts.rs_insert_in)

            # mocked input and output
            m.submodules.output = self.out = TestbenchIO(method_rs_insert)
            m.submodules.rs_allocate = self.rs_allocate = TestbenchIO(method_rs_alloc)
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
                rs_alloc=method_rs_alloc.iface,
                rs_insert=method_rs_insert.iface,
                gen_params=self.gen_params,
            )

        return tm


class TestScheduler(TestCaseWithSimulator):
    def setUp(self):
        self.gen_params = GenParams("rv32i")
        self.expected_rename_queue = queue.Queue()
        self.expected_phys_reg_queue = queue.Queue()
        self.free_regs_queue = queue.Queue()
        self.free_ROB_entries_queue = queue.Queue()
        self.expected_rs_entry_queue = queue.Queue()
        self.current_RAT = [0 for _ in range(0, self.gen_params.isa.reg_cnt)]
        self.instr_count = 500
        self.m = SchedulerTestCircuit(self.gen_params)

        random.seed(42)

        # set up static RF state lookup table
        RFEntry = namedtuple("RFEntry", ["value", "valid"])
        self.RF_state = [
            RFEntry(random.randint(0, self.gen_params.isa.xlen - 1), random.randint(0, 1))
            for _ in range(2**self.gen_params.phys_regs_bits)
        ]
        self.RF_state[0] = RFEntry(0, 1)

        for i in range(1, 2**self.gen_params.phys_regs_bits):
            self.free_phys_reg(i)

    def free_phys_reg(self, reg_id):
        self.free_regs_queue.put({"data": reg_id})
        self.expected_phys_reg_queue.put(reg_id)

    def queue_gather(self, queues: Iterable[queue.Queue]):
        # Iterate over all 'queues' and take one element from each, gathering
        # all key-value pairs into 'item'.
        item = {}
        for q in queues:
            partial_item = None
            # retry until we get an element
            while partial_item is None:
                try:
                    # get element from one queue
                    partial_item = q.get_nowait()
                    # None signals to end the process
                    if partial_item is None:
                        return None
                except queue.Empty:
                    # if no element available, wait and retry on the next clock cycle
                    yield
                else:
                    # merge queue element with all previous ones (dict merge)
                    item = item | partial_item
        return item

    def make_queue_process(
        self,
        *,
        io: TestbenchIO,
        input_queues: Optional[Iterable[queue.Queue]] = None,
        output_queues: Optional[Iterable[queue.Queue]] = None,
        check: Optional[Callable[[RecordIntDict, RecordIntDict], TestGen[None]]] = None,
    ):
        """Create queue gather-and-test process

        This function returns a simulation process that does the following steps:
        1. Gathers dicts from multiple ``queues`` (one dict from each) and joins
           them together
        2. ``io`` is called with items gathered from ``input_queues``
        3. If ``check`` was supplied, it's called with the results returned from
           call in step 2. and items gathered from ``output_queues``
        Steps 1-3 are repeated until one of the queues receives None

        Intention is to simplify writing tests with queues: ``input_queues`` lets
        the user specify multiple data sources (queues) from which to gather
        arguments for call to ``io``, and multiple data sources (queues) from which
        to gather reference values to test against the results from the call to ``io``.

        Parameters
        ----------
        io : TestbenchIO
            TestbenchIO to call with items gathered from ``input_queues``.
        input_queues : Queue[dict], optional
            Queue of dictionaries containing fields and values of a record to call
            ``io`` with. Different fields may be split across multiple queues.
            Fields with the same name in different queues must not be used.
        output_queues : Queue[dict], optional
            Queue of dictionaries containing reference fields and values to compare
            results of ``io`` call with. Different fields may be split across
            multiple queues. Fields with the same name in different queues must
            not be used,
        check : Callable[[dict, dict], TestGen]
            Testbench generator which will be called with parameters ``result``
            and ``outputs``, meaning results from the call to ``io`` and item
            gathered from ``output_queues``.

        Returns
        -------
        Callable[None, TestGen]
            Simulation process performing steps described above.

        Raises
        ------
        ValueError
            If neither ``input_queues`` nor ``output_queues`` are supplied.
        """

        def queue_process():
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

                # this could possibly be extended to automatically compare 'results' and
                # 'outputs' if check is None but that needs some dict deepcompare
                if check is not None:
                    yield Settle()
                    yield from check(result, outputs)

        if output_queues is None and input_queues is None:
            raise ValueError("Either output_queues or input_queues must be supplied")

        return queue_process

    def make_output_process(self):
        def after_call(got, expected):
            rl_dst = yield self.m.rob.data[got["rob_id"]].rob_data.rl_dst
            s1 = self.RF_state[expected["rp_s1"]]
            s2 = self.RF_state[expected["rp_s2"]]

            # if source operand register ids are 0 then we already have values
            self.assertEqual(got["rp_s1"], expected["rp_s1"] if not s1.valid else 0)
            self.assertEqual(got["rp_s2"], expected["rp_s2"] if not s2.valid else 0)
            self.assertEqual(got["rp_dst"], expected["rp_dst"])
            self.assertEqual(got["opcode"], expected["opcode"])
            self.assertEqual(got["rs_entry_id"], expected["rs_entry_id"])
            self.assertEqual(got["s1_val"], s1.value if s1.valid else 0)
            self.assertEqual(got["s2_val"], s2.value if s2.valid else 0)
            self.assertEqual(rl_dst, expected["rl_dst"])

            # recycle physical register number
            if got["rp_dst"] != 0:
                self.free_phys_reg(got["rp_dst"])
            # recycle ROB entry
            self.free_ROB_entries_queue.put({"rob_id": got["rob_id"]})

        return self.make_queue_process(
            io=self.m.out, output_queues=[self.expected_rename_queue, self.expected_rs_entry_queue], check=after_call
        )

    def test_randomized(self):
        def instr_input_process():
            yield from self.m.rob_retire.enable()

            # set up RF to reflect our static RF_state reference lookup table
            for i in range(2**self.gen_params.phys_regs_bits - 1):
                yield from self.m.rf_write.call({"reg_id": i, "reg_val": self.RF_state[i].value})
                if not self.RF_state[i].valid:
                    yield from self.m.rf_free.call({"reg_id": i})

            for i in range(self.instr_count):
                rl_s1 = random.randint(0, self.gen_params.isa.reg_cnt - 1)
                rl_s2 = random.randint(0, self.gen_params.isa.reg_cnt - 1)
                rl_dst = random.randint(0, self.gen_params.isa.reg_cnt - 1)
                # Note: opcode is currently a placeholder
                opcode = random.randint(0, 2**32 - 1)
                rp_s1 = self.current_RAT[rl_s1]
                rp_s2 = self.current_RAT[rl_s2]
                rp_dst = self.expected_phys_reg_queue.get() if rl_dst != 0 else 0

                self.expected_rename_queue.put(
                    {"rp_s1": rp_s1, "rp_s2": rp_s2, "rl_dst": rl_dst, "rp_dst": rp_dst, "opcode": opcode}
                )
                self.current_RAT[rl_dst] = rp_dst

                yield from self.m.instr_inp.call({"rl_s1": rl_s1, "rl_s2": rl_s2, "rl_dst": rl_dst, "opcode": opcode})

            # Terminate other processes
            self.expected_rename_queue.put(None)
            self.free_regs_queue.put(None)
            self.free_ROB_entries_queue.put(None)

        def rs_alloc_process():
            for i in range(self.instr_count):
                random_entry = random.randint(0, self.gen_params.rs_entries - 1)
                self.expected_rs_entry_queue.put({"rs_entry_id": random_entry})
                yield from self.m.rs_allocate.call({"entry_id": random_entry})
            self.expected_rs_entry_queue.put(None)

        with self.runSimulation(self.m) as sim:
            sim.add_sync_process(self.make_output_process())
            sim.add_sync_process(
                self.make_queue_process(io=self.m.rob_done, input_queues=[self.free_ROB_entries_queue])
            )
            sim.add_sync_process(self.make_queue_process(io=self.m.free_rf_inp, input_queues=[self.free_regs_queue]))
            sim.add_sync_process(instr_input_process)
            sim.add_sync_process(rs_alloc_process)
