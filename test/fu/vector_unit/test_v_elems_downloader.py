from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_elems_downloader import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.transactions.lib import *
from test.fu.vector_unit.common import *


class TestVectorElemsDownloader(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.vrp_count = 8
        self.gen_params = GenParams(test_vector_core_config.replace(vector_config=VectorUnitConfiguration(vrp_count = self.vrp_count)))
        self.test_number = 100
        self.v_params = self.gen_params.v_params

        self.layout = VectorBackendLayouts(self.gen_params)

        vrf = VRFFragment(gen_params = self.gen_params)
        self.fu_receiver = MethodMock(i=self.layout.fu_data_in)
        self.circ = SimpleTestCircuit(VectorElemsDownloader(self.gen_params, vrf.read_req, vrf.read_resp, self.fu_receiver.get_method()))

        self.m = ModuleConnector(circ = self.circ, fu_receiver = self.fu_receiver, vrf = vrf)

        self.received_data = deque()

    @def_method_mock(lambda self: self.fu_receiver)
    def fu_receiver_process(self, arg):

