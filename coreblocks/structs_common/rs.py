from typing import Iterable, Optional, Type, Generic, TypeVar, Callable
from typing_extensions import Self
from amaranth import *
from amaranth.lib.coding import PriorityEncoder
from coreblocks.transactions import Method, def_method, TModule, loop_def_method
from coreblocks.params import RSLayouts, GenParams, OpType
from coreblocks.transactions.core import RecordDict
from coreblocks.utils.protocols import RSLayoutProtocol
from coreblocks.utils.utils import mod_incr, assign, AssignType, MultiPriorityEncoder

__all__ = ["RS", "FifoRS"]


T = TypeVar("T", bound=RSLayoutProtocol)


class RS(Elaboratable, Generic[T]):
    def __init__(
        self,
        gen_params: GenParams,
        rs_entries: int,
        ready_for: Optional[Iterable[Iterable[OpType]]] = None,
        *,
        layout_class: Type[T] = RSLayouts,
        custom_rec_ready_setter: Optional[Callable[[Self, TModule], None]] = None,
        superscalarity : int = 1
    ) -> None:
        self.superscalarity = superscalarity
        self.custom_rec_ready_setter = custom_rec_ready_setter
        ready_for = ready_for or ((op for op in OpType),)
        self.gen_params = gen_params
        self.rs_entries = rs_entries
        self.rs_entries_bits = (rs_entries - 1).bit_length()
        self.layouts = gen_params.get(layout_class, rs_entries_bits=self.rs_entries_bits)
        self.internal_layout = [
            ("rs_data", self.layouts.data_layout),
            ("rec_full", 1),
            ("rec_ready", 1),
            ("rec_reserved", 1),
        ]

        if self.superscalarity<1:
            raise ValueError("Requested less than 1 input port.")

        self.insert_list = [Method(i=self.layouts.insert_in, name="insert{i}") for i in range(self.superscalarity)]
        self.insert = self.insert_list[0]
        self.select_list = [Method(o=self.layouts.select_out) for _ in range(self.superscalarity)]
        self.select = self.select_list[0]
        self.update = Method(i=self.layouts.update_in)
        self.take = Method(i=self.layouts.take_in, o=self.layouts.take_out)

        self.ready_for = [list(op_list) for op_list in ready_for]
        self.get_ready_list = [Method(o=self.layouts.get_ready_list_out, nonexclusive=True) for _ in self.ready_for]

        self.data = Array(Record(self.internal_layout) for _ in range(self.rs_entries))

    def define_update_method(self, m: TModule):
        @def_method(m, self.update)
        def _(tag: Value, value: Value) -> None:
            for record in self.data:
                with m.If(record.rec_full.bool()):
                    with m.If(record.rs_data.rp_s1 == tag):
                        m.d.sync += record.rs_data.rp_s1.eq(0)
                        m.d.sync += record.rs_data.s1_val.eq(value)

                    with m.If(record.rs_data.rp_s2 == tag):
                        m.d.sync += record.rs_data.rp_s2.eq(0)
                        m.d.sync += record.rs_data.s2_val.eq(value)

    def generate_rec_ready_setters(self, m):
        if self.custom_rec_ready_setter is not None:
            self.custom_rec_ready_setter(self, m)
        else:
            for record in self.data:
                m.d.comb += record.rec_ready.eq(
                    ~record.rs_data.rp_s1.bool() & ~record.rs_data.rp_s2.bool() & record.rec_full.bool()
                )

    def elaborate(self, platform):
        m = TModule()

        m.submodules.enc_select = encoder =  MultiPriorityEncoder(input_width=self.rs_entries, outputs_count=self.superscalarity)

        self.generate_rec_ready_setters(m)

        select_vector = Cat(~record.rec_reserved for record in self.data)
        select_possible = select_vector.any()

        take_vector = Cat(record.rec_ready & record.rec_full for record in self.data)
        take_possible = take_vector.any()

        ready_lists: list[Value] = []
        for op_list in self.ready_for:
            op_vector = Cat(Cat(record.rs_data.exec_fn.op_type == op for op in op_list).any() for record in self.data)
            ready_lists.append(take_vector & op_vector)

        m.d.comb += encoder.input.eq(select_vector)

        @loop_def_method(m, self.select_list, ready_list=encoder.valids)
        def _(i:int) -> Signal:
            m.d.sync += self.data[encoder.outputs[i]].rec_reserved.eq(1)
            return encoder.outputs[i]

        @loop_def_method(m, self.insert_list)
        def _(_:int, rs_entry_id: Value, rs_data: Value) -> None:
            m.d.sync += self.data[rs_entry_id].rs_data.eq(rs_data)
            m.d.sync += self.data[rs_entry_id].rec_full.eq(1)
            m.d.sync += self.data[rs_entry_id].rec_reserved.eq(1)

        self.define_update_method(m)

        @def_method(m, self.take, ready=take_possible)
        def _(rs_entry_id: Value) -> RecordDict:
            record = self.data[rs_entry_id]
            m.d.sync += record.rec_reserved.eq(0)
            m.d.sync += record.rec_full.eq(0)
            record_out = Record(self.layouts.take_out)
            m.d.comb += assign(record_out, record.rs_data, fields=AssignType.COMMON)
            return record_out

        @loop_def_method(m, self.get_ready_list, ready_list=lambda i: ready_lists[i].any())
        def _(i) -> RecordDict:
            return {"ready_list": ready_lists[i]}

        return m


class FifoRS(RS[T]):
    """Fifo RS

    Implementation of RS interface, which ignores `rs_entry_id` and instead of that
    operates as fifo, so new elements are added to the end of the RS, and an element
    can be take iff it is ready and is on the head.
    """

    # TODO: Instead of creating separate class maybe it will be enough to add proper
    # selection and taken logic to normal RS?
    def __init__(
        self, gen_params: GenParams, rs_entries: int, ready_for: Optional[Iterable[Iterable[OpType]]] = None, **kwargs
    ) -> None:
        super().__init__(gen_params, rs_entries, ready_for, **kwargs)
        self.first_empty = Signal(self.rs_entries_bits)
        self.oldest_full = Signal(self.rs_entries_bits)

    def elaborate(self, platform):
        m = TModule()

        @def_method(m, self.select)
        def _():
            # ignore rs_entry_id because we always insert data to first empty slot
            return
    
        next_after_empty = Signal().like(self.first_empty)
        m.d.top_comb += next_after_empty.eq(mod_incr(self.first_empty, self.rs_entries))
        @def_method(m, self.insert, ready= next_after_empty != self.oldest_full)
        def _(rs_entry_id, rs_data):
            m.d.sync += self.data[self.first_empty].rs_data.eq(rs_data)
            m.d.sync += self.data[self.first_empty].rec_full.eq(1)
            m.d.sync += self.first_empty.eq(next_after_empty)

        self.define_update_method(m)
        self.generate_rec_ready_setters(m)

        @def_method(m, self.take, ready=self.data[self.oldest_full].rec_ready)
        def _(rs_entry_id):
            record = self.data[self.oldest_full]
            m.d.sync += self.oldest_full.eq(mod_incr(self.oldest_full, self.rs_entries))
            m.d.sync += record.rec_reserved.eq(0)
            m.d.sync += record.rec_full.eq(0)
            record_out = Record(self.layouts.take_out)
            m.d.comb += assign(record_out, record.rs_data, fields=AssignType.COMMON)
            return record_out

        ready_lists: list[Value] = []
        for op_list in self.ready_for:
            op_correct = Cat(self.data[self.oldest_full].rs_data.exec_fn.op_type == op for op in op_list).any()
            ready_lists.append(
                self.data[self.oldest_full].rec_ready & self.data[self.oldest_full].rec_full & op_correct
            )

        @loop_def_method(m, self.get_ready_list, ready_list=lambda i: ready_lists[i].any())
        def _(i) -> RecordDict:
            return {"ready_list": ready_lists[i]}

        return m
