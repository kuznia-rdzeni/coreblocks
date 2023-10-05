from amaranth import *
from test.common import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.params.configurations import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.v_input_verification import *
from collections import deque, defaultdict


class TestVInstructionVerification(TestCaseWithSimulator):
    def setUp(self):
        self.maxDiff = None
        random.seed(14)
        self.gen_params = GenParams(test_vector_core_config)
        self.test_number = 100
        self.v_params = self.gen_params.v_params

        self.vf_layout = VectorFrontendLayouts(self.gen_params)
        self.rob_block_interrupts = TestbenchIO(Adapter(i=ROBLayouts(self.gen_params).block_interrupts))
        self.put_instr = TestbenchIO(Adapter(i=self.vf_layout.verification_out))
        self.get_vill = TestbenchIO(Adapter(o=self.vf_layout.get_vill))
        self.get_vstart = TestbenchIO(Adapter(o=self.vf_layout.get_vstart))
        self.retire = TestbenchIO(Adapter(i=FuncUnitLayouts(self.gen_params).accept))
        self.exception_report = TestbenchIO(Adapter(i=self.gen_params.get(ExceptionRegisterLayouts).report))
        self.gen_params.get(DependencyManager).add_dependency(ExceptionReportKey(), self.exception_report.adapter.iface)

        self.circ = SimpleTestCircuit(
            VectorInputVerificator(
                self.gen_params,
                self.rob_block_interrupts.adapter.iface,
                self.put_instr.adapter.iface,
                self.get_vill.adapter.iface,
                self.get_vstart.adapter.iface,
                self.retire.adapter.iface,
            )
        )

        self.m = ModuleConnector(
            circ=self.circ,
            rob_block_interrupts=self.rob_block_interrupts,
            put_instr=self.put_instr,
            get_vill=self.get_vill,
            get_vstart=self.get_vstart,
            retire=self.retire,
            report=self.exception_report,
        )

    def check_ok(self, data, rbi, put):
        self.assertEqual(len(data), len(rbi))
        self.assertEqual(len(data), len(put))

        for orginal, rbi, put in zip(data, rbi, put):
            self.assertDictEqual(orginal, put)
            self.assertEqual(orginal["rob_id"], rbi)

    def test_passing(self):
        data_q = deque()
        rbi_q = deque()
        put_q = deque()
        retire_q = deque()
        report_q = deque()

        def create_mocks():
            @def_method_mock(lambda: self.rob_block_interrupts)
            def rbi(rob_id):
                rbi_q.append(rob_id)

            @def_method_mock(lambda: self.put_instr)
            def put_instr(arg):
                put_q.append(arg)

            @def_method_mock(lambda: self.get_vill)
            def get_vill():
                return {"vill": 0}

            @def_method_mock(lambda: self.get_vstart)
            def get_vstart():
                return {"vstart": 0}

            @def_method_mock(lambda: self.retire)
            def retire(rob_id, result, rp_dst, exception):
                self.assertTrue(retire_q, f"rob_id: {rob_id}")
                data = retire_q.popleft()
                self.assertEqual(exception, 1)
                self.assertEqual(rp_dst, data["rp_dst"])

            @def_method_mock(lambda: self.exception_report)
            def report(rob_id, cause):
                self.assertTrue(report_q, f"rob_id: {rob_id}")
                report_q.popleft()
                self.assertEqual(ExceptionCause.ILLEGAL_INSTRUCTION, cause)

            return rbi, put_instr, get_vill, get_vstart, retire, report

        def _get_load_store_width(funct3):
            try:
                return eew_to_bits(load_store_width_to_eew(funct3))
            except ValueError:
                return 64

        def process():
            for _ in range(self.test_number):
                data = generate_instr(self.gen_params, self.vf_layout.verification_in, support_vector=True)
                if (
                    data["exec_fn"]["op_type"] in [OpType.V_LOAD, OpType.V_STORE]
                    and _get_load_store_width(data["exec_fn"]["funct3"]) > self.v_params.elen
                ):
                    retire_q.append(data)
                    report_q.append(data)
                else:
                    data_q.append(data)
                yield from self.circ.issue.call(data)
            # wait few cycles to be sure that all mocks were called
            for _ in range(2):
                yield
            self.check_ok(data_q, rbi_q, put_q)

        with self.run_simulation(self.m) as sim:
            for mock in create_mocks():
                sim.add_sync_process(mock)
            sim.add_sync_process(process)

    def test_failing(self):
        data_q_fail = deque()
        data_q_pass = deque()
        retire_q = deque()
        report_q = deque()
        vill_q = defaultdict(int)
        vstart_q = defaultdict(int)
        rbi_q = deque()
        put_q = deque()

        def create_mocks():
            @def_method_mock(lambda: self.rob_block_interrupts)
            def rbi(rob_id):
                rbi_q.append(rob_id)

            @def_method_mock(lambda: self.put_instr)
            def put_instr(arg):
                put_q.append(arg)

            @def_method_mock(lambda: self.get_vill)
            def get_vill(*, _now):
                ret = {"vill": vill_q[_now]}
                return ret

            @def_method_mock(lambda: self.get_vstart)
            def get_vstart(*, _now):
                ret = {"vstart": vstart_q[_now]}
                return ret

            @def_method_mock(lambda: self.retire)
            def retire(arg):
                retire_q.append(arg)

            @def_method_mock(lambda: self.exception_report)
            def report(arg):
                report_q.append(arg)

            return rbi, put_instr, get_vill, get_vstart, retire, report

        def process():
            for _ in range(self.test_number):
                data = generate_instr(self.gen_params, self.vf_layout.verification_in, support_vector=True)
                now = yield Now()
                if vill := random.randrange(2):
                    vstart_q[now] = 0
                else:
                    vstart_q[now] = 1
                vill_q[now] = vill

                yield from self.circ.issue.call(data)
                if (data["exec_fn"]["op_type"] == OpType.V_CONTROL) and vill:
                    data_q_pass.append(data)
                else:
                    data_q_fail.append(data)
                yield from self.tick(random.randrange(4))

            # wait few cycles to be sure that all mocks were called
            for _ in range(2):
                yield

            self.assertEqual(len(data_q_fail), len(retire_q))
            self.assertEqual(len(data_q_fail), len(report_q))

            for orginal, retire_data, report_data in zip(data_q_fail, retire_q, report_q):
                for field in ["rp_dst", "rob_id"]:
                    self.assertEqual(orginal[field], retire_data[field])
                self.assertEqual(1, retire_data["exception"])
                self.assertEqual(orginal["rob_id"], report_data["rob_id"])
                self.assertEqual(ExceptionCause.ILLEGAL_INSTRUCTION, report_data["cause"])

            self.check_ok(data_q_pass, rbi_q, put_q)

        with self.run_simulation(self.m) as sim:
            for mock in create_mocks():
                sim.add_sync_process(mock)
            sim.add_sync_process(process)
