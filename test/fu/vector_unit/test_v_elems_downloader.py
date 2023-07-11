from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_elems_downloader import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.transactions.lib import *
from test.fu.vector_unit.common import *
from collections import deque
from parameterized import parameterized_class


@parameterized_class(["seed", "wait_ppb"], [(14,0), (15,0.7)])
class TestVectorElemsDownloader(TestCaseWithSimulator):
    seed : int
    wait_ppb : float
    def setUp(self):
        random.seed(self.seed)
        self.vrp_count = 8
        self.gen_params = GenParams(test_vector_core_config.replace(vector_config=VectorUnitConfiguration(vrp_count = self.vrp_count)))
        self.test_number = 10
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)

        vrf = VRFFragment(gen_params = self.gen_params)
        self.fu_receiver = MethodMock(i=self.layout.fu_data_in)
        self.circ = SimpleTestCircuit(VectorElemsDownloader(self.gen_params, vrf.read_req, vrf.read_resp, self.fu_receiver.get_method()))
        self.write = TestbenchIO(AdapterTrans(vrf.write))

        self.m = ModuleConnector(circ = self.circ, fu_receiver = self.fu_receiver, vrf = vrf)

        self.received_data = deque()

        self.memory = {i: [0]*self.v_params.elens_in_bank for i in range(self.v_params.vrp_count)}

    @def_method_mock(lambda self: self.fu_receiver, enable = lambda self : random.random() >= self.wait_ppb)
    def fu_receiver_process(self, arg):
        self.received_data.append(arg)


    def memory_write(self, vrp_id):
        for i in range(self.v_params.elens_in_bank):
            val = random.randrange(2**self.v_params.elen)
            yield from self.write.call(addr=i, data=val, valid_mask = 2**self.v_params.bytes_in_elen-1)
            self.memory[vrp_id][i] = val

    def generate_input(self):
        return {
            "elems_len" : random.randrange(1, self.v_params.elens_in_bank),
            "s1" : random.randrange(self.v_params.vrp_count),
            "s2" : random.randrange(self.v_params.vrp_count),
            "s3" : random.randrange(self.v_params.vrp_count),
            "v0" : random.randrange(self.v_params.vrp_count),
            "s1_needed" : random.randrange(2),
            "s2_needed" : random.randrange(2),
            "s3_needed" : random.randrange(2),
            "v0_needed" : random.randrange(2),
        }

    def check_register(self, expected, field_name):
        vrp_id = expected[field_name]
        for i,elem in enumerate(self.received_data):
            self.assertEqual(elem[field_name], self.memory[vrp_id][i])

    def process(self):
        print("START")
        self.assertFalse(True)
        for i in range(self.v_params.vrp_count):
            yield from self.memory_write(i)

        for _ in range(self.test_number):
            self.received_data.clear()
            input = self.generate_input()
            yield from self.circ.issue.call(input)
            while len(self.received_data) < input["elems_len"]:
                yield

            for field_name in ["s1", "s2", "s3", "v0"]:
                self.check_register(input, field_name)

            self.memory_write(random.randrange(self.v_params.vrp_count))

    def test_random(self):
        print("TUT")
        with self.run_simulation(self.m, 300) as sim:
            print("TUT2")
            sim.add_sync_process(self.process)
