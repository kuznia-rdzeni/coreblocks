import random
from test.common import *
from coreblocks.lsu.vector_lsu import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.params.configurations import *
from test.fu.vector_unit.common import *
from collections import deque
from coreblocks.peripherals.wishbone import *
from test.peripherals.test_wishbone import WishboneInterfaceWrapper

class VRFStub():
    def __init__(self, gen_params : GenParams):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.write = MethodMock(i = self.gen_params.get(VRFFragmentLayouts).write)
        self.read_req = MethodMock(i = self.gen_params.get(VRFFragmentLayouts).read_req)
        self.read_resp = MethodMock(o = self.gen_params.get(VRFFragmentLayouts).read_resp_o)

        self.methods = ModuleConnector(write = self.write, read_req = self.read_req, read_resp = self.read_resp)

        self.regs = [[0 for __ in range(self.v_params.elens_in_bank)] for _ in range(self.v_params.vrp_count)]
        self.reqs = deque()

    @def_method_mock(lambda self: self.write)
    def write_process(self, vrp_id, addr, valid_mask, value):
        expanded = expand_mask(valid_mask)
        self.regs[vrp_id][addr] = (self.regs[vrp_id][addr] & ~expanded) | (expanded & value)

    @def_method_mock(lambda self: self.read_req, sched_prio = 1)
    def read_req_process(self, arg):
        self.reqs.append(arg)

    @def_method_mock(lambda self: self.read_resp, enable = lambda self: self.reqs)
    def read_resp_process(self):
        req = self.reqs.popleft()
        return {"data": self.regs[req["vrp_id"]][req["addr"]]}


class TestVectorLSU(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(
            test_vector_core_config.replace(vector_config=VectorUnitConfiguration(vrp_count=8, _vrl_count=7))
        )
        self.test_number = 40
        self.v_params = self.gen_params.v_params
        wb_params = WishboneParameters( data_width=self.v_params.elen, addr_width=32)
        self.layouts = self.gen_params.get(VectorLSULayouts)

        self.exception_report = MethodMock(i=self.gen_params.get(ExceptionRegisterLayouts).report)
        self.vrfs = [VRFStub(self.gen_params) for _ in range(self.v_params.register_bank_count)]

        self.bus = WishboneMaster(wb_params)
        self.wishbone = WishboneInterfaceWrapper(self.bus)

        self.gen_params.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.get_method())
        self.circ = SimpleTestCircuit(VectorLSU(self.gen_params, self.bus, [vrf.write.get_method() for vrf in self.vrfs], [vrf.read_req.get_method() for vrf in self.vrfs], [vrf.read_resp.get_method() for vrf in self.vrfs]))
        self.m = ModuleConnector(circ = self.circ, vrfs = ModuleConnector(*[vrf.methods for vrf in self.vrfs], bus = self.bus, exception_report = self.exception_report))

        self.generator = get_vector_instr_generator()
        self.current_instr = None

    @def_method_mock(lambda self:self.exception_report)
    def exception_process(self, arg):
        pass


    def wishbone_process(self):
        yield Passive()
        current_elen = 0
        while True:
            yield from self.wishbone.slave_wait()
            self.assertIsNotNone(self.current_instr)
            assert self.current_instr is not None
            elens_to_check = self.current_instr["vtype"]["vl"]/(self.v_params.elen // eew_to_bits(self.current_instr["vtype"]["sew"]))

            is_load = self.current_instr["exec_fn"]["op_type"] == OpType.V_LOAD
            if is_load:
                exp_data = 0
                exp_sel = 0
            else:
                exp_data = self.vrfs[current_elen//self.v_params.elens_in_bank].regs[self.current_instr["rp_s3"]["id"]][current_elen%self.v_params.elens_in_bank]
                if current_elen + 1 == elens_to_check:
                    #kilka ostatnich
                else:
                    exp_sel = 2**self.v_params.bytes_in_elen -1

            yield from self.wishbone.slave_verify(self.current_instr["s1_val"]//4 + current_elen, exp_data, is_load, exp_sel)
            current_elen += 1
            if current_elen == elens_to_check:
                pass

    def insert_process(self):
        for _ in range(self.test_number):
            instr, vtype = self.generator(self.gen_params, self.layouts.rs_data_layout, const_lmul = LMUL.m1,
                                   optypes=[OpType.V_LOAD, OpType.V_STORE], funct3 = [Funct3.VMEM8, Funct3.VMEM16, Funct3.VMEM32], max_reg_bits = 3,
                                   overwriting = {"rp_s3" : {"type": RegisterType.V},"rp_dst" : {"type": RegisterType.V}})
            self.current_instr = instr
            yield from self.circ.select.call()
            yield from self.circ.insert.call(rs_data = instr, rs_entry_id = 0)
            yield from self.circ.update.call(tag = instr["rp_s3"], value = 0)

            result = yield from self.circ.get_result.call()

    def precommit_process(self):
        yield Passive()
        while True:
            if self.current_instr is None:
                yield
            else:
                yield from self.circ.precommit.call(rob_id = self.current_instr["rob_id"])

    def test_random(self):
        VRFStub(self.gen_params)
