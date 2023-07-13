from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_mask_extractor import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.transactions.lib import *
from test.fu.vector_unit.common import *
from collections import deque
from parameterized import parameterized_class


class TestVectorMaskExtractor(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 100
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)

        self.put = MethodMock(i = self.layout.mask_extractor_out)
        self.circ = SimpleTestCircuit(VectorMaskExtractor(self.gen_params, self.put.get_method()))
        self.m = ModuleConnector(circ=self.circ, put=self.put)
        
        self.received_data = None

    @def_method_mock(lambda self: self.put, sched_prio = 1)
    def put_process(self, mask):
        self.received_data = mask

    def generate_input(self):
        while True:
            eew = random.choice(list(EEW))
            if eew_to_bits(eew) <= self.v_params.elen:
                break
        return {
                "v0" : random.randrange(2**self.v_params.elen),
                "elen_index" : random.randrange(self.v_params.elens_in_bank),
                "eew" : eew,
                "vm" : random.randrange(2),
                }

    def check(self, input):
        if input["vm"]:
            self.assertEqual(self.received_data, 2**self.v_params.bytes_in_elen -1)
            return
        part_width = self.v_params.elen // eew_to_bits(input["eew"])
        parts_in_elen = self.v_params.elen // part_width # for each `input` this is equal to eew_to_bits(input["eew"])
        idx = input["elen_index"] % parts_in_elen
        elem_mask = (input["v0"] >> (idx*part_width)) & (2**part_width - 1)
        mask = elem_mask_to_byte_mask(self.v_params.elen, elem_mask, input["eew"])
        self.assertEqual(mask, self.received_data)


    def process(self):
        for _ in range(self.test_number):
            input = self.generate_input()
            yield from self.circ.issue.call(input)
            self.assertIsNotNone(self.received_data)
            self.check(input)
            self.received_data = None

    def test_random(self):
        with self.run_simulation(self.m) as sim:
            sim.add_sync_process(self.process)
            sim.add_sync_process(self.put_process)
