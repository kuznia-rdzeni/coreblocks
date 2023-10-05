from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_elems_uploader import *
from coreblocks.fu.vector_unit.vrf import *
from test.fu.vector_unit.common import *
from collections import deque
from parameterized import parameterized_class


@parameterized_class(["seed", "wait_ppb"], [(14, 0), (15, 0.7)])
class TestVectorElemsUploader(TestCaseWithSimulator):
    seed: int
    wait_ppb: float

    def setUp(self):
        random.seed(self.seed)
        self.vrp_count = 8
        self.gen_params = GenParams(
            test_vector_core_config.replace(
                vector_config=VectorUnitConfiguration(vrp_count=self.vrp_count, _vrl_count=7)
            )
        )
        self.test_number = 30
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)

        self.write = MethodMock(i=self.vrf_layout.write)
        self.read_old_dst = MethodMock(o=self.layout.uploader_old_dst_in)
        self.read_mask = MethodMock(o=self.layout.uploader_mask_in)
        self.report_end = MethodMock()
        self.circ = SimpleTestCircuit(
            VectorElemsUploader(
                self.gen_params,
                self.write.get_method(),
                self.read_old_dst.get_method(),
                self.read_mask.get_method(),
                self.report_end.get_method(),
            )
        )
        self.m = ModuleConnector(
            circ=self.circ,
            write=self.write,
            read_old_dst=self.read_old_dst,
            read_mask=self.read_mask,
            report_end=self.report_end,
        )

        self.received_data = deque()
        self.send_old_dst = deque()
        self.send_mask = deque()
        self.send_new_dst = deque()
        self.end_raised = False

    @def_method_mock(lambda self: self.report_end, sched_prio=1)
    def report_end_process(self):
        self.end_raised = True

    @def_method_mock(lambda self: self.write, enable=lambda self: random.random() >= self.wait_ppb, sched_prio=1)
    def write_process(self, arg):
        self.received_data.append(arg)

    @def_method_mock(lambda self: self.read_old_dst)
    def read_old_dst_process(self):
        old_dst = random.randrange(2**self.v_params.elen)
        self.send_old_dst.append(old_dst)
        return {"old_dst_val": old_dst}

    @def_method_mock(lambda self: self.read_mask)
    def read_mask_process(self):
        mask = random.randrange(2**self.v_params.bytes_in_elen)
        self.send_mask.append(mask)
        return {"mask": mask}

    def check(self, vrp_id, elens_len):
        for i, (recv, new_dst, old_dst, mask) in enumerate(
            reversed(list(zip(self.received_data, self.send_new_dst, self.send_old_dst, self.send_mask)))
        ):
            self.assertEqual(recv["addr"], i)
            self.assertEqual(recv["vrp_id"], vrp_id)
            self.assertEqual(recv["valid_mask"], 2**self.v_params.bytes_in_elen - 1)
            self.assertEqual(recv["data"], (expand_mask(mask) & new_dst) | (~expand_mask(mask) & old_dst))

    def process(self):
        for _ in range(self.test_number):
            vrp_id = random.randrange(self.v_params.vrp_count)
            ma = random.randrange(2)
            elens_len = random.randrange(1, self.v_params.elens_in_bank)
            yield from self.circ.init.call(ma=ma, vrp_id=vrp_id, elens_len=elens_len)
            self.assertFalse(self.end_raised)
            while len(self.received_data) < elens_len:
                new_dst = random.randrange(2**self.v_params.elen)
                self.send_new_dst.append(new_dst)
                self.assertFalse(self.end_raised)
                yield from self.circ.issue.call(dst_val=new_dst)
            self.assertEqual(len(self.received_data), len(self.send_new_dst))
            self.assertEqual(len(self.received_data), len(self.send_old_dst))
            self.assertEqual(len(self.received_data), len(self.send_mask))
            self.assertTrue(self.end_raised)

            self.check(vrp_id, elens_len)

            self.send_mask.clear()
            self.received_data.clear()
            self.send_old_dst.clear()
            self.send_new_dst.clear()
            self.end_raised = False

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.read_old_dst_process)
            sim.add_sync_process(self.read_mask_process)
            sim.add_sync_process(self.write_process)
            sim.add_sync_process(self.report_end_process)
