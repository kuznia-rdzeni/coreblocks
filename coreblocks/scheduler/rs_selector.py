from typing import Tuple

from amaranth import *

from coreblocks.params import OpType, GenParams, SchedulerLayouts
from coreblocks.transactions import Method, Transaction
from coreblocks.utils import assign


class OpTypeDecoder(Elaboratable):
    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.optype_in = Signal(OpType)
        self.decoded = Signal(len(OpType))

    def elaborate(self, platform):
        m = Module()

        for op in OpType:
            with m.If(self.optype_in == op):
                m.d.comb += self.decoded[op - OpType.UNKNOWN].eq(1)

        return m


def decoded_optype_set(optypes: set[OpType]) -> int:
    res = 0x0
    for op in optypes:
        res |= 1 << op - OpType.UNKNOWN
    return res


# currently it do no load balancing, and only selects first available RS
class RSSelector(Elaboratable):
    def __init__(
        self, gen_params: GenParams, get_instr: Method, rs_select: list[Tuple[Method, set[OpType]]], push_instr: Method
    ):
        self.gen_params = gen_params

        layouts = gen_params.get(SchedulerLayouts)
        self.input_layout = layouts.rs_select_in
        self.output_layout = layouts.rs_select_out

        self.get_instr = get_instr
        self.rs_select = rs_select
        self.push_instr = push_instr

    def elaborate(self, platform):
        m = Module()
        m.submodules.decoder = decoder = OpTypeDecoder(self.gen_params)

        with Transaction().body(m):
            for i in range(len(self.rs_select)):
                alloc, optypes = self.rs_select[i]
                data_out = Record(self.output_layout)

                instr = self.get_instr(m)

                m.d.comb += decoder.optype_in.eq(instr.exec_fn.op_type)
                with m.If((decoder.decoded & decoded_optype_set(optypes)).bool()):
                    allocated_field = alloc(m)

                    m.d.comb += assign(data_out, instr)
                    m.d.comb += data_out.rs_entry_id.eq(allocated_field.rs_entry_id)
                    m.d.comb += data_out.rs_selected.eq(i)

                    self.push_instr(m, data_out)

        return m
