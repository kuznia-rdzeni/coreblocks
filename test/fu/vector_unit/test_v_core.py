from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_core import *
from test.fu.vector_unit.common import *
from collections import deque

class TestVectorCore(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 50
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

    @def_method_mock(lambda self: self.rob_block_interrupt)
    def rob_block_interrupt_process(self, arg):
        pass

    @def_method_mock(lambda self: self.rob_peek)
    def rob_peek_process(self):
        return {"rob_data" : 0, "rob_id" : 0, "exception" : 0}

    @def_method_mock(lambda self: self.exception_report_process)
    def exception_report_process(self, arg):
        pass

    def generate_input(self):
        instr, vtype = self.generator(self.gen_params, self.vxrs_layouts.data_layout, support_vector = True, optypes = [OpType.V_ARITHMETIC], funct7 = generate_funct7_from_funct6(get_funct6_to_op(EEW.w8).keys()),
                                      max_vl = self.v_params.vlen // 8,
                                      funct3 = [Funct3.OPIVI, Funct3.OPIVV, Funct3.OPIVX],
                                      not_balanced_vsetvl = True,
                                      const_lmul = LMUL.m1,
                                      random_rob_id = False)
        to_correct = {}
        if instr["exec_fn"]["op_type"] ==OpType.V_ARITHMETIC:
            to_correct |= {"rp_s2" : {"type": RegisterType.V}, "rp_dst" : {"type": RegisterType.V}}
        if instr["exec_fn"]["funct3"] == Funct3.OPIVV:
            to_correct |= {"rp_s1" : {"type" : RegisterType.V}}
        if instr["exec_fn"]["funct3"] in [Funct3.OPIVI, Funct3.OPIVX]:
            to_correct |= {"rp_s1" : {"type" : RegisterType.X}}
        return overwrite_dict_values(instr, to_correct)

    def input_process(self):
        for _ in range(self.test_number):
            print(self.generate_input())

    def test_liveness(self):
        with self.run_simulation(self.m, 100) as sim:
            sim.add_sync_process(self.input_process)
            sim.add_sync_process(self.rob_block_interrupt_process)
            sim.add_sync_process(self.rob_peek_process)
            sim.add_sync_process(self.exception_report_process)
