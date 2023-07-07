import math
from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_status import *
from coreblocks.fu.vector_unit.v_frontend import VectorFrontend
from coreblocks.structs_common.rat import FRAT
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from test.fu.vector_unit.common import *
from collections import deque
import copy


class TestVectorFrontend(TestCaseWithSimulator):
    def setUp(self):
        random.seed(15)
        #  216 - OK, 217 NOK
        self.test_number = 217
        self.gen_params = GenParams(test_core_config)
        self.v_params = VectorParameters(vlen = 1024, elen = 32)
        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)

        self.generate_vector_instr = get_vector_instr_generator()

        self.rob_block_interrupt = MethodMock(i= self.gen_params.get(ROBLayouts).block_interrupts)
        self.put_mem = MethodMock(i=self.layouts.instr_to_mem)
        self.put_vvrs = MethodMock(i=self.layouts.instr_to_vvrs)
        self.retire = MethodMock(i=FuncUnitLayouts(self.gen_params).accept)
        self.retire_mult = MethodMock(i=self.layouts.translator_report_multiplier)
        self.exception_report = MethodMock(i=self.gen_params.get(ExceptionRegisterLayouts).report)
        self.gen_params.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.get_method())
        self.frat = FRAT(gen_params = self.gen_params, superscalarity = 2)
        self.freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1)
        self.deallocate = TestbenchIO(AdapterTrans(self.freerf.deallocates[0]))
        self.circ = SimpleTestCircuit(VectorFrontend(self.gen_params, self.v_params, self.rob_block_interrupt.get_method(),
                                                     self.retire.get_method(), self.retire_mult.get_method(), self.freerf.allocate,
                                                     self.frat.get_rename_list[0], self.frat.get_rename_list[1], self.frat.set_rename_list[0],
                                                     self.put_mem.get_method(), self.put_vvrs.get_method()))
        self.m = ModuleConnector(
                circ = self.circ,
                frat = self.frat,
                freerf = self.freerf,
                rob_block_interrupt = self.rob_block_interrupt,
                put_mem = self.put_mem,
                put_vvrs = self.put_vvrs,
                retire = self.retire,
                retire_mult = self.retire_mult,
                exception_report = self.exception_report,
                deallocate = self.deallocate,
                )

        self.orginal_instr = deque()
        self.to_dealocate = deque()
        self.received_instr=deque()
        self.received_instr_mem=deque()
        self.received_block_interrupt = deque()
        self.received_retire = deque()
        self.received_mult = deque()
        self._robs = deque()
        self._org_robs = deque()
        

    @def_method_mock(lambda self: self.exception_report)
    def report_process(self, arg):
        self.assertTrue(False)

    @def_method_mock(lambda self: self.put_vvrs)
    def put_vvrs_process(self, arg):
        self.to_dealocate.append(arg["rp_dst"]["id"])
        #print("rob_id", arg["rob_id"])
        self._robs.append(arg["rob_id"])
        self.received_instr.append(arg)

    @def_method_mock(lambda self: self.put_mem)
    def put_mem_process(self, arg):
        self.to_dealocate.append(arg["rp_dst"]["id"])
        self._robs.append(arg["rob_id"])
        self.received_instr_mem.append(arg)

    @def_method_mock(lambda self: self.rob_block_interrupt)
    def rob_block_interrupt_process(self, arg):
        self.received_block_interrupt.append(arg)

    @def_method_mock(lambda self: self.retire)
    def retire_process(self, arg):
        self.received_retire.append(arg)

    @def_method_mock(lambda self: self.retire_mult)
    def mult_process(self, mult):
        self.received_mult.append(mult)


    def input_process(self):
        for i in range(self.test_number):
            instr, vtype = self.generate_vector_instr(self.gen_params, self.v_params, self.layouts.verification_in)
            while instr["exec_fn"]["op_type"] == OpType.V_CONTROL and instr["rp_s1"]["id"] == instr["rp_s2"]["id"]:
                instr, vtype = self.generate_vector_instr(self.gen_params, self.v_params, self.layouts.verification_in)
            print(i)
            print(instr)
            print(vtype)
            self.orginal_instr.append((instr, vtype))
            if instr["exec_fn"]["op_type"] != OpType.V_CONTROL:
                self._org_robs.append(instr["rob_id"])
            yield from self.circ.select.call()
            yield from self.circ.insert.call(rs_entry_id=0, rs_data = instr)
            yield from self.circ.update.call(tag = instr["rp_s1"], value = instr["s1_val"])
            yield from self.circ.update.call(tag = instr["rp_s2"], value = instr["s2_val"])
            yield from self.tick(random.randrange(3))
        print("KONIEC WEJSCIA")

    def remove_duplicates(self, lista):
        nowa =[lista[0]]
        for e in lista:
            if nowa[-1]!=e:
                nowa.append(e)
        return nowa


    def checker(self):
        while len(self.received_mult) + len(self.received_retire) < self.test_number:
            if (yield Now())==4900:
                print(len(self.received_mult) , len(self.received_retire))
                print(len(self.received_instr), len(self.received_instr_mem))
                print(self.received_mult)
                print(sum(self.received_mult))
                print(self._robs)
                print(self.remove_duplicates(self._robs)[200:])
                print(list(self._org_robs)[200:])
                #self.assertIterableEqual(self.remove_duplicates(self._robs), self._org_robs)
            yield
        # be sure that there is no other instructions in pipeline
        yield from self.tick(10)
        self.assertEqual(len(self.received_mult) + len(self.received_retire), self.test_number)

        def compare_fields(org_instr, vtype, list_to_pop):
            lmul = lmul_to_int(vtype["lmul"])
            for _ in range(lmul):
                retired_instr = list_to_pop.popleft()
                print(retired_instr)
                self.assertFieldsEqual(org_instr, retired_instr, ["rob_id", "exec_fn"])

        for org_instr, vtype in self.orginal_instr:
            print("----------------")
            print(org_instr, vtype)
            if org_instr["exec_fn"]["op_type"]==OpType.V_CONTROL:
                retired_instr = self.received_retire.popleft()
                self.assertFieldsEqual(org_instr, retired_instr, ["rob_id", "rp_dst"])
            elif org_instr["exec_fn"]["op_type"]==OpType.V_MEMORY:
                compare_fields(org_instr, vtype, self.received_instr_mem)
            else:
                compare_fields(org_instr, vtype, self.received_instr)
    
    def deallocator_process(self):
        yield Passive()
        while True:
            if self.to_dealocate:
                reg = self.to_dealocate.popleft()
                yield from self.deallocate.call(reg=reg)
            yield
            #yield from self.tick(random.randrange(3))

    def test_random(self):
        with self.run_simulation(self.m, 5000) as sim:
            sim.add_sync_process(self.checker)
            sim.add_sync_process(self.input_process)
            sim.add_sync_process(self.put_vvrs_process)
            sim.add_sync_process(self.put_mem_process)
            sim.add_sync_process(self.rob_block_interrupt_process)
            sim.add_sync_process(self.retire_process)
            sim.add_sync_process(self.mult_process)
            sim.add_sync_process(self.report_process)
            sim.add_sync_process(self.deallocator_process)

    #TODO test z stałym LMUL=8
