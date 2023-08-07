from amaranth.sim import *
from collections import deque
from parameterized import parameterized_class
from test.common import *
from test.fu.vector_unit.common import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.params.configurations import *


def generate_write(vp: VectorParameters):
    data = random.randrange(2**vp.elen)
    addr = random.randrange(vp.elens_in_bank)
    mask = random.randrange(2**vp.bytes_in_elen)
    vrp_id = random.randrange(vp.vrp_count)
    return {"data": data, "addr": addr, "valid_mask": mask, "vrp_id": vrp_id}


def generate_read_req(vp: VectorParameters):
    addr = random.randrange(vp.elens_in_bank)
    vrp_id = random.randrange(vp.vrp_count)
    return {"addr": addr, "vrp_id": vrp_id}


@parameterized_class(("wait_chance",), [(0.005,), (0.3,)])
class TestVRFFragment(TestCaseWithSimulator):
    wait_chance: float

    def setUp(self):
        gp = GenParams(
            test_vector_core_config.replace(
                vector_config=VectorUnitConfiguration(
                    vlen=128, elen=32, vrp_count=8, register_bank_count=1, _vrl_count=7
                )
            )
        )
        self.vp = gp.v_params
        self.circ = SimpleTestCircuit(VRFFragment(gen_params=gp))
        self.read_port_count = 4

        self.test_iterations = 10
        self.iteration_len = 10
        self.reference_memory = [
            [2**self.vp.elen - 1 for __ in range(self.vp.elens_in_bank)] for _ in range(self.vp.vrp_count)
        ]
        self.expected_reads = [deque() for i in range(self.read_port_count)]
        self.received_reads = deque()
        self.passive_requestors = 0
        self.passive_receivers = 0
        self.barierr_writer = SimBarrier(1+self.read_port_count)
        self.read_cond_var = CondVar(transparent = False)

    def writer(self):
        for __ in range(self.test_iterations):
            for _ in range(self.iteration_len):
                req = generate_write(self.vp)
                yield from self.circ.write.call(req)
                yield Settle()
                current_val = self.reference_memory[req["vrp_id"]][req["addr"]]
                new_val = (req["data"] & expand_mask(req["valid_mask"])) | (current_val & ~expand_mask(req["valid_mask"]))
                self.reference_memory[req["vrp_id"]][req["addr"]] = new_val
                while random.random() < self.wait_chance:
                    yield
            yield from self.read_cond_var.notify()
            yield from self.barierr_writer.wait()

    def generate_read_requestor(self, k):
        def f():
            for __ in range(self.test_iterations):
                yield from self.read_cond_var.wait()
                for _ in range(self.iteration_len):
                    req = generate_read_req(self.vp)
                    yield from self.circ.read_req[k].call(req)
                    self.expected_reads[k].append(self.reference_memory[req["vrp_id"]][req["addr"]])
                    while random.random() < self.wait_chance:
                        yield
                yield from self.barierr_writer.wait()
        return f

    def generate_read_receiver(self, k):
        def f():
            for _ in range(self.test_iterations*self.iteration_len):
                resp = yield from self.circ.read_resp[k].call()
                self.assertIn(resp["data"], self.expected_reads[k])
                self.expected_reads[k].remove(resp["data"])
                while random.random() < self.wait_chance:
                    yield
        return f

    def test_random(self):
        with self.run_simulation(self.circ, 5000) as sim:
            sim.add_sync_process(self.writer)
            for i in range(self.read_port_count):
                sim.add_sync_process(self.generate_read_receiver(i))
                sim.add_sync_process(self.generate_read_requestor(i))
