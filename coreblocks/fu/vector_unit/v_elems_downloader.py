from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VectorElemsDownloader"]

class VectorElemsDownloader(Elaboratable):
    def __init__(self, gen_params : GenParams, read_req_list : list[Method], read_resp_list : list[Method], send_to_fu : Method):
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.read_req_list = [NotMethod(m) for m in read_req_list]
        self.read_resp_list = [NotMethod(m) for m in read_resp_list]
        self.send_to_fu = send_to_fu

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vrf_layout = VRFFragmentLayouts(self.gen_params)
        self.issue = Method(i = self.layouts.downloader_in)

    def elaborate(self, platform):
        m = TModule()

        regs_number = 4

        instr = Record(self.layouts.downloader_in)
        instr_valid = Signal(name = "instr_valid")
        req_counter = Signal(self.v_params.elens_in_bank_bits, name= "req_counter")
        resp_counter = Signal(self.v_params.elens_in_bank_bits, name="resp_counter")
        m.submodules.uniqness_checker = uniqness_checker = PriorityUniqnessChecker(regs_number, self.gen_params.phys_regs_bits)

        regs_fields = ["s1", "s2", "s3", "v0"]
        for i, field in enumerate(regs_fields):
            m.d.comb += uniqness_checker.inputs[i].eq(instr[field])

        needed_signals = Signal(regs_number)
        m.d.top_comb += needed_signals.eq(
                Cat(instr[field] for i, field in enumerate(["s1_needed", "s2_needed", "s3_needed", "v0_needed"])))
        m.d.top_comb += Cat(uniqness_checker.input_valids).eq(needed_signals)

        fifos_to_vrf = [FIFO(self.vrf_layout.read_req, 2) for _ in range(regs_number)]
        m.submodules.fifos_to_vrf = ModuleConnector(*fifos_to_vrf)

        fifos_to_resp_in = [FIFO(self.vrf_layout.read_resp_i, 4) for _ in range(regs_number)]
        m.submodules.fifos_to_resp_in = ModuleConnector(*fifos_to_resp_in)

        barrier = Barrier(self.vrf_layout.read_resp_o, regs_number)
        m.submodules.barrier = barrier

        m.submodules.connect_req = ModuleConnector(* [ConnectTrans(fifos_to_vrf[i].read, self.read_req_list[i].method) for i in range(regs_number)])
        for i in range(regs_number):
            with Transaction().body(m):
                arg = fifos_to_resp_in[i].read(m)
                barrier.write_list[i](m, self.read_resp_list[i].method(m, arg))

        with Transaction(name = "downloader_request_trans").body(m, request = instr_valid & (req_counter != 0)):
            addr = Signal(range(self.v_params.elens_in_bank))
            m.d.top_comb += addr.eq(req_counter - 1)
            for i, field_name in enumerate(regs_fields):
                with m.If (uniqness_checker.valids[i] & instr[field_name + "_needed"]):
                    fifos_to_vrf[i].write(m, vrp_id = instr[field_name], addr = addr)
                    fifos_to_resp_in[i].write(m, vrp_id = instr[field_name])
            m.d.sync += req_counter.eq(addr)


        data_to_fu = Record(self.layouts.downloader_data_out)
        with Transaction(name = "downloader_response_trans").body(m, request = instr_valid & (resp_counter != 0)):
            barrier_out = barrier.read(m)
            for i, field in enumerate(regs_fields):
                with m.If(needed_signals.bit_select(i,1)):
                    with m.If(uniqness_checker.valids[i]):
                        m.d.comb += data_to_fu[field].eq(barrier_out[f"out{i}"])
                    with m.Else():
                        for j in reversed(range(i)):
                            with m.If(uniqness_checker.valids[j] & needed_signals.bit_select(j, 1) & (instr[field] == instr[regs_fields[j]])):
                                m.d.comb += data_to_fu[field].eq(barrier_out[f"out{j}"])

            m.d.sync += resp_counter.eq(resp_counter-1)
            self.send_to_fu(m, data_to_fu)
            with m.If(resp_counter == 1):
                m.d.sync += instr_valid.eq(0)
                barrier.set_valids(m, valids = (2**regs_number-1))


        uniq= Signal(4, name="uniq")
        m.d.top_comb += uniq.eq(Cat(uniqness_checker.valids))
        set_valids_to_barrier = Signal()
        with Transaction().body(m, request = set_valids_to_barrier):
            barrier.set_valids(m, valids = uniq & needed_signals)
            m.d.sync += set_valids_to_barrier.eq(0)


        @def_method(m, self.issue, ready = ~instr_valid)
        def _(arg):
            m.d.sync += instr.eq(arg)
            m.d.sync += instr_valid.eq(1)
            m.d.sync += req_counter.eq(arg.elens_len)
            m.d.sync += resp_counter.eq(arg.elens_len)
            m.d.sync += set_valids_to_barrier.eq(1)

        return m
