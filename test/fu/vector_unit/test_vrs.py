from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import VectorXRSLayout
from amaranth.utils import bits_for
import copy

def get_reg_id(instr, name):
    return instr["rs_data"][name]["id"]
def get_reg_type(instr, name):
    return instr["rs_data"][name]["type"]

def set_reg_id(instr, name, new_id):
    instr["rs_data"][name]["id"]=new_id

def set_s_val(instr, val_name, val):
    instr["rs_data"][val_name] = val

class TestVXRS(TestCaseWithSimulator):

    def setUp(self):
        self.gen_params = GenParams(test_core_config)
        self.rs_entries = 8
        self.circ  = SimpleTestCircuit(VXRS(self.gen_params, self.rs_entries))

    def generate_input(self):
        input =[]
        for i in range(self.rs_entries):
            data = generate_instr(self.gen_params, VectorXRSLayout(self.gen_params, rs_entries_bits = bits_for(self.rs_entries-1)).data_layout,support_vector=True, overwriting={"rp_s1":{"id":i*2}, "rp_s2":{"id":i*2+1}})
            instr={}
            instr ["rs_data"] = data
            instr ["rs_entry_id"] = i
            input.append(instr)
        return input

    def insert_input(self, input):
        for instr in input:
            yield from self.circ.insert.call(instr)

    def update_register(self, instr, name, val_name):
        if get_reg_id(instr, name) == 0 or get_reg_type(instr, name) == RegisterType.V:
            return 
        val = random.randrange(2**32-1)
        yield from self.circ.update.call(tag=instr["rs_data"][name], value=val)
        set_reg_id(instr, name, 0)
        set_s_val(instr, val_name, val)

    def assert_ready(self, record, instr):
        s1_id = get_reg_id(instr, "rp_s1")
        s2_id = get_reg_id(instr, "rp_s2")
        s1_type = get_reg_type(instr, "rp_s1")
        s2_type = get_reg_type(instr, "rp_s2")
        yield Settle()
        if s1_type==RegisterType.X and s1_id !=0:
            self.assertEqual((yield record.rec_ready), 0)
            return
        if s2_type==RegisterType.X and s2_id !=0:
            self.assertEqual((yield record.rec_ready), 0)
            return
        self.assertEqual((yield record.rec_ready), 1)

    def process(self, input):
        def f():
            yield from self.insert_input(input)
            for id in range(self.rs_entries):
                instr = input[id]
                self.assertTrue((yield self.circ._dut.data[id].rec_full))
                yield from self.assert_ready(self.circ._dut.data[id], instr)
                yield from self.update_register(instr, "rp_s1", "s1_val")
                yield from self.assert_ready(self.circ._dut.data[id], instr)
                yield from self.update_register(instr, "rp_s2", "s2_val")
                yield from self.assert_ready(self.circ._dut.data[id], instr)
                yield from self.circ.take.call(rs_entry_id=0)
        return f

    def test_readiness(self):
        input = self.generate_input()
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.process(input))
