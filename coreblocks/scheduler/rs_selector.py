from typing import Tuple

from amaranth import *

from coreblocks.params import OpType, GenParams, SchedulerLayouts
from coreblocks.transactions import Method, Transaction, def_method
from coreblocks.transactions._utils import MethodLayout
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


class ForwarderWithLookup(Elaboratable):
    """Forwarding with lookup

    Forwarder but with lookup record.

    Attributes
    ----------
    read: Method
        The read method. Accepts an empty argument, returns a `Record`.
    write: Method
        The write method. Accepts a `Record`, returns empty result.
    lookup: Record
        The record where we can look up currently stored value.
    """

    def __init__(self, layout: MethodLayout):
        """
        Parameters
        ----------
        layout: int or record layout
            The format of records forwarded.
        """
        self.read = Method(o=layout)
        self.write = Method(i=layout)
        self.lookup = Record(layout)

    def elaborate(self, platform):
        m = Module()

        reg = Record.like(self.read.data_out)
        reg_valid = Signal()
        read_value = Record.like(self.read.data_out)

        m.d.comb += self.lookup.eq(Mux(reg_valid, reg, read_value))

        self.write.schedule_before(self.read)  # to avoid combinational loops

        @def_method(m, self.write, ready=~reg_valid)
        def _(arg):
            Method.comb += read_value.eq(arg)  # for forwarding
            m.d.sync += reg.eq(arg)
            m.d.sync += reg_valid.eq(1)

        @def_method(m, self.read, ready=reg_valid | self.write.run)
        def _(arg):
            with m.If(reg_valid):
                m.d.comb += read_value.eq(reg)  # write method is not ready
            m.d.sync += reg_valid.eq(0)
            return read_value

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
        m.submodules.forwarder = forwarder = ForwarderWithLookup(self.input_layout)

        m.d.comb += decoder.optype_in.eq(forwarder.lookup.exec_fn.op_type)

        with Transaction().body(m):
            instr = self.get_instr(m)
            forwarder.write(m, instr)

        data_out = Record(self.output_layout)

        for i in range(len(self.rs_select)):
            alloc, optypes = self.rs_select[i]

            with Transaction().body(m, request=(decoder.decoded & decoded_optype_set(optypes)).bool()):
                instr = forwarder.read(m)
                allocated_field = alloc(m)

                m.d.comb += assign(data_out, instr)
                m.d.comb += data_out.rs_entry_id.eq(allocated_field.rs_entry_id)
                m.d.comb += data_out.rs_selected.eq(i)

                self.push_instr(m, data_out)

        return m
