from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_core import *
from test.fu.vector_unit.common import *
from collections import deque
from parameterized import parameterized_class

#@parameterized_class(["seed"], [ (i,) for i in range(82, 89)])
class TestVectorCore(TestCaseWithSimulator):
    seed : int
    def setUp(self):
        random.seed(75)
        self.gen_params = GenParams(test_vector_core_config.replace(vector_config = VectorUnitConfiguration(register_bank_count = 1, vrp_count = 36)))
        self.test_number = 350
        self.v_params = self.gen_params.v_params

        self.vxrs_layouts = VectorXRSLayout(
            self.gen_params, rs_entries_bits=log2_int(self.v_params.vxrs_entries, False)
        )

        self.rob_block_interrupt = MethodMock(i=self.gen_params.get(ROBLayouts).block_interrupts)
        self.rob_peek = MethodMock(o=self.gen_params.get(ROBLayouts).peek_layout)
        self.exception_report = MethodMock(i=self.gen_params.get(ExceptionRegisterLayouts).report)
        self.gen_params.get(DependencyManager).add_dependency(ROBBlockInterruptsKey(), self.rob_block_interrupt.get_method())
        self.gen_params.get(DependencyManager).add_dependency(ROBPeekKey(), self.rob_peek.get_method())
        self.gen_params.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.get_method())

        self.circ = SimpleTestCircuit(VectorCore(self.gen_params))
        self.m = ModuleConnector(circ =self.circ, rob_block_interrupt = self.rob_block_interrupt, rob_peek = self.rob_peek, exception_report = self.exception_report)


        self.generator = get_vector_instr_generator()
        self.instr_q = deque()
        self.instr_ended_q = deque()
        self.lowest_used_rob_id = 0

    @def_method_mock(lambda self: self.rob_block_interrupt)
    def rob_block_interrupt_process(self, arg):
        pass

    @def_method_mock(lambda self: self.rob_peek, sched_prio = 1)
    def rob_peek_process(self):
#        print("INSTR   ", self.instr_q)
        if self.instr_q:
#            print("ZNALEZIONO")
            rob_oldest = self.instr_q[0]
            return {"rob_data" : {"rp_dst" : rob_oldest["rp_dst"], "rl_dst" : rob_oldest["rp_dst"] }, "rob_id" : rob_oldest["rob_id"], "exception" : 0}
        else:
            return {"rob_data" : {"rp_dst" : 0xFF, "rl_dst" : 0xFF }, "rob_id" : 0xFF, "exception" : 1}

    @def_method_mock(lambda self: self.exception_report)
    def exception_report_process(self, arg):
        print("EXCEPTION!")
        print(arg)
        self.assertFalse(True)

    def generate_input(self):
        instr, vtype = self.generator(self.gen_params, self.vxrs_layouts.data_layout, support_vector = True, optypes = [OpType.V_ARITHMETIC], funct7 = generate_funct7_from_funct6(get_funct6_to_op(EEW.w8).keys()),
                                      max_vl = self.v_params.vlen // 8,
                                      funct3 = [Funct3.OPIVI, Funct3.OPIVV, Funct3.OPIVX],
                                      not_balanced_vsetvl = True,
                                      const_lmul = LMUL.m1,
                                      vsetvl_different_rp_id = True,
                                      random_rob_id = False)
        to_correct = {}
        if instr["exec_fn"]["op_type"] ==OpType.V_ARITHMETIC:
            to_correct |= {"rp_s2" : {"type": RegisterType.V}, "rp_dst" : {"type": RegisterType.V}}
        if instr["exec_fn"]["funct3"] == Funct3.OPIVV:
            to_correct |= {"rp_s1" : {"type" : RegisterType.V}}
        if instr["exec_fn"]["funct3"] in [Funct3.OPIVI, Funct3.OPIVX]:
            to_correct |= {"rp_s1" : {"type" : RegisterType.X}}
        print(instr["rob_id"], vtype)
        return overwrite_dict_values(instr, to_correct)

    def input_process(self):
        for _ in range(self.test_number):
            print("----------------")
            input = self.generate_input()
            print(input)
            while input["rob_id"] + 1 == self.lowest_used_rob_id:
                yield
            self.instr_q.append(input)
            rs_entry_id = (yield from self.circ.select.call())["rs_entry_id"]
            yield from self.circ.insert.call(rs_data = input, rs_entry_id = rs_entry_id)
            if input["rp_s1"]["type"] == RegisterType.X and input["rp_s1"]["id"] != 0:
                yield from self.circ.update.call(tag = input["rp_s1"], value = input["s1_val"])
            if input["rp_s2"]["type"] == RegisterType.X and input["rp_s2"]["id"] != 0:
                yield from self.circ.update.call(tag = input["rp_s2"], value = input["s2_val"])

    def output_process(self):
        for _ in range(self.test_number):
            result = yield from self.circ.get_result.call()
            self.instr_ended_q.append(result)
            print("CYCLE:", (yield Now()))
            print("ENDED:", result)

    def find_rob_id_in_ended(self, rob_id):
        for ended in self.instr_ended_q:
            if ended["rob_id"] == rob_id:
                return True
        return False

    def remove_rob_id_from_ended(self, rob_id):
        for ended in self.instr_ended_q:
            if ended["rob_id"] == rob_id:
                self.instr_ended_q.remove(ended)
                return
        self.assertFalse(True)

    def find_instr_in_rob(self, rob_id):
        for instr in self.instr_q:
            if instr["rob_id"] == rob_id:
                return instr
        self.assertFalse(True, "Expected instruction not found.")
        assert False

    def check_ordering(self):
        current = self.instr_q[0]
        rob_id = current["rob_id"]
        self.assertEqual(current["rob_id"], rob_id, "Expected rob_id not on head of rob.")
        for ended in self.instr_ended_q:
            if ended["rob_id"] == rob_id:
                break
            earlier_ended_instr = self.find_instr_in_rob(ended["rob_id"])

            if current["rp_dst"]["id"] == 0 and current["rp_dst"]["type"] == RegisterType.V:
                # check that writing to V0 serialise vector arithmetic instructions (as all vector instructions
                # potentialy depends on vector mask from v0) in other words no V_ARITHMETIC
                # instruction ended execution earlier
                self.assertEqual(earlier_ended_instr["exec_fn"]["op_type"], OpType.V_CONTROL)
            else:
                for field in ["rp_s1", "rp_s2", "rp_dst"]:
                    # check that each instruction that was executed earlier hasn't
                    # depended on currently calculated value
                    self.assertNotEqual(earlier_ended_instr[field], current["rp_dst"], f"{field}; head rob_id: {rob_id}, ended rob_id: {ended['rob_id']}")

    def precommit_process(self):
        for _ in range(self.test_number):
            while not self.instr_q:
                yield
            rob_oldest = self.instr_q[0]
            self.assertEqual(self.lowest_used_rob_id, rob_oldest["rob_id"])
            while True:
                res = yield from self.circ.precommit.call_try(rob_id = rob_oldest["rob_id"])
                if not self.find_rob_id_in_ended(rob_oldest["rob_id"]):
                    self.assertIsNotNone(res)
                else:
                    break
            print("CYCLE:", (yield Now()))
            print("Commiting:", rob_oldest)
            self.check_ordering()
            self.remove_rob_id_from_ended(rob_oldest["rob_id"])
            self.lowest_used_rob_id = (self.lowest_used_rob_id + 1) % 2**self.gen_params.rob_entries_bits
            self.instr_q.popleft()

    def test_liveness(self):
        with self.run_simulation(self.m, 7000) as sim:
            sim.add_sync_process(self.input_process)
            sim.add_sync_process(self.output_process)
            sim.add_sync_process(self.precommit_process)
            sim.add_sync_process(self.rob_block_interrupt_process)
            sim.add_sync_process(self.rob_peek_process)
            sim.add_sync_process(self.exception_report_process)
