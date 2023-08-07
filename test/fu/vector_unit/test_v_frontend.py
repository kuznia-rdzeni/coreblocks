from amaranth import *
from test.common import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_frontend import VectorFrontend
from coreblocks.structs_common.rat import FRAT
from coreblocks.structs_common.superscalar_freerf import SuperscalarFreeRF
from test.fu.vector_unit.common import *
from collections import deque


class TestVectorFrontend(TestCaseWithSimulator):
    def setUp(self):
        self.test_number = 40
        self.gen_params = GenParams(test_vector_core_config)
        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.v_params = self.gen_params.v_params

        self.generate_vector_instr = get_vector_instr_generator()

        self.rob_block_interrupt = MethodMock(i=self.gen_params.get(ROBLayouts).block_interrupts)
        self.put_mem = MethodMock(i=self.layouts.instr_to_mem)
        self.put_vvrs = MethodMock(i=self.layouts.instr_to_vvrs)
        self.announce = MethodMock(i=FuncUnitLayouts(self.gen_params).accept)
        self.announce2 = MethodMock(i=FuncUnitLayouts(self.gen_params).accept)
        self.exception_report = MethodMock(i=self.gen_params.get(ExceptionRegisterLayouts).report)
        self.gen_params.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.get_method())
        self.frat = FRAT(gen_params=self.gen_params, superscalarity=2)
        self.freerf = SuperscalarFreeRF(self.v_params.vrp_count, 1)
        self.deallocate = TestbenchIO(AdapterTrans(self.freerf.deallocates[0]))
        self.initialise_list = [MethodMock() for _ in range(self.v_params.vrp_count)]
        self.initialise_process_list = []
        self.circ = SimpleTestCircuit(
            VectorFrontend(
                self.gen_params,
                self.rob_block_interrupt.get_method(),
                self.announce.get_method(),
                self.announce2.get_method(),
                self.freerf.allocate,
                self.frat.get_rename_list[0],
                self.frat.get_rename_list[1],
                self.frat.set_rename_list[0],
                self.put_mem.get_method(),
                self.put_vvrs.get_method(),
                [mock.get_method() for mock in self.initialise_list],
            )
        )
        self.m = ModuleConnector(
            circ=self.circ,
            frat=self.frat,
            freerf=self.freerf,
            rob_block_interrupt=self.rob_block_interrupt,
            put_mem=self.put_mem,
            put_vvrs=self.put_vvrs,
            announce=self.announce,
            announce2=self.announce2,
            exception_report=self.exception_report,
            deallocate=self.deallocate,
            initialise=ModuleConnector(*self.initialise_list),
        )

        self.orginal_instr = deque()
        self.to_dealocate = deque()
        self.received_instr = deque()
        self.received_instr_mem = deque()
        self.received_block_interrupt = deque()
        self.received_announce = deque()
        self._robs = deque()
        self._org_robs = deque()
        self.initialise_requests = deque()

        for i in range(self.v_params.vrp_count):

            def create_mock(i):
                @def_method_mock(lambda: self.initialise_list[i], sched_prio=1)
                def f():
                    self.initialise_requests.append(i)

                return f

            self.initialise_process_list.append(create_mock(i))

    @def_method_mock(lambda self: self.exception_report)
    def report_process(self, arg):
        # We don't expect any errors
        self.assertTrue(False)

    @def_method_mock(lambda self: self.put_vvrs)
    def put_vvrs_process(self, arg):
        if arg["rp_dst"]["type"] == RegisterType.V:
            self.to_dealocate.append(arg["rp_dst"]["id"])
        self._robs.append(arg["rob_id"])
        self.received_instr.append(arg)

    @def_method_mock(lambda self: self.put_mem)
    def put_mem_process(self, arg):
        if arg["rp_dst"]["type"] == RegisterType.V:
            self.to_dealocate.append(arg["rp_dst"]["id"])
        self._robs.append(arg["rob_id"])
        self.received_instr_mem.append(arg)

    @def_method_mock(lambda self: self.rob_block_interrupt)
    def rob_block_interrupt_process(self, arg):
        self.received_block_interrupt.append(arg)

    @def_method_mock(lambda self: self.announce)
    def announce_process(self, arg):
        self.received_announce.append(arg)

    @def_method_mock(lambda self: self.announce2)
    def announce2_process(self, arg):
        self.received_announce.append(arg)

    def input_process(self, generator):
        def f():
            for i in range(self.test_number):
                instr, vtype = generator()
                self.orginal_instr.append((instr, vtype))
                if instr["exec_fn"]["op_type"] != OpType.V_CONTROL:
                    self._org_robs.append(instr["rob_id"])
                yield from self.circ.select.call()
                yield from self.circ.insert.call(rs_entry_id=0, rs_data=instr)
                if instr["rp_s1"]["id"] != 0:
                    yield from self.circ.update.call(tag=instr["rp_s1"], value=instr["s1_val"])
                if instr["rp_s2"]["id"] != 0:
                    yield from self.circ.update.call(tag=instr["rp_s2"], value=instr["s2_val"])
                yield from self.tick(random.randrange(3))

        return f

    def remove_duplicates(self, lista):
        nowa = [lista[0]]
        for e in lista:
            if nowa[-1] != e:
                nowa.append(e)
        return nowa

    def checker(self):
        while len(self.received_instr) + len(self.received_instr_mem) + len(self.received_announce) < self.test_number:
            yield
        # be sure that there is no other instructions in pipeline
        yield from self.tick(2)
        self.assertEqual(len(self.received_instr) + len(self.received_instr_mem) + len(self.received_announce), self.test_number)

        def compare_fields(org_instr, vtype, list_to_pop):
            announced_instr = list_to_pop.popleft()
            self.assertFieldsEqual(org_instr, announced_instr, ["rob_id", "exec_fn"])

        for org_instr, vtype in self.orginal_instr:
            if org_instr["exec_fn"]["op_type"] == OpType.V_CONTROL:
                announced_instr = self.received_announce.popleft()
                self.assertFieldsEqual(org_instr, announced_instr, ["rob_id", "rp_dst"])
            elif org_instr["exec_fn"]["op_type"] in [OpType.V_LOAD, OpType.V_STORE]:
                compare_fields(org_instr, vtype, self.received_instr_mem)
            else:
                compare_fields(org_instr, vtype, self.received_instr)

    def deallocator_process(self):
        yield Passive()
        while True:
            if self.to_dealocate:
                reg = self.to_dealocate.popleft()
                initialised_reg = self.initialise_requests.popleft()
                self.assertEqual(reg, initialised_reg)
                yield from self.deallocate.call(reg=reg)
            yield from self.tick(random.randrange(3))

    def test_random(self):
        random.seed(14)
        with self.run_simulation(self.m, 500) as sim:
            sim.add_sync_process(self.checker)
            sim.add_sync_process(
                self.input_process(
                    lambda: self.generate_vector_instr(
                        self.gen_params, self.layouts.verification_in, vsetvl_different_rp_id=True
                    )
                )
            )
            sim.add_sync_process(self.put_vvrs_process)
            sim.add_sync_process(self.put_mem_process)
            sim.add_sync_process(self.rob_block_interrupt_process)
            sim.add_sync_process(self.announce_process)
            sim.add_sync_process(self.announce2_process)
            sim.add_sync_process(self.report_process)
            sim.add_sync_process(self.deallocator_process)
            for f in self.initialise_process_list:
                sim.add_sync_process(f)
