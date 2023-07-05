from amaranth import *
from typing import Optional, Iterable
from coreblocks.transactions import *
from coreblocks.structs_common.rs import FifoRS, RS
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *

__all__ = ["VXRS"]


class VXRS(FifoRS):
    """Vector extension RS to wait for scalars

    This is a RS, which extends the FifoRS with `rec_ready` signals to
    specialise it for the usage as RS that wait only for scalars values.
    """

    def __init__(
        self,
        gen_params: GenParams,
        rs_entries: int,
        ready_for: Optional[Iterable[Iterable[OpType]]] = None,
    ) -> None:
        super().__init__(gen_params, rs_entries, ready_for, layout_class=VectorXRSLayout)

    def generate_rec_ready_setters(self, m: TModule):
        for record in self.data:
            is_rs1_ready = (record.rs_data.rp_s1.type == RegisterType.X).implies(~record.rs_data.rp_s1.id.bool())
            is_rs2_ready = (record.rs_data.rp_s2.type == RegisterType.X).implies(~record.rs_data.rp_s2.id.bool())
            m.d.comb += record.rec_ready.eq(is_rs1_ready & is_rs2_ready & record.rec_full.bool())


class VVRS(RS):
    def __init__(self,
        gen_params: GenParams,
        rs_entries: int,
        ready_for: Optional[Iterable[Iterable[OpType]]] = None,
    ) -> None:
        super().__init__(gen_params, rs_entries, ready_for, layout_class=VectorVRSLayout, superscalarity = 8)

    def generate_rec_ready_setters(self, m: TModule):
        for record in self.data:
            m.d.comb += record.rec_ready.eq(
                    record.rs_data.rp_s1_rdy &
                    record.rs_data.rp_s2_rdy &
                    record.rs_data.rp_s3_rdy &
                    record.rec_full.bool()
                    )

    def define_update_method(self, m: TModule):
        @def_method(m, self.update)
        def _(tag: Value, value: Value) -> None:
            for record in self.data:
                with m.If(record.rec_full.bool()):
                    with m.If(record.rs_data.rp_s1 == tag):
                        m.d.sync += record.rs_data.rp_s1_rdy.eq(1)

                    with m.If(record.rs_data.rp_s2 == tag):
                        m.d.sync += record.rs_data.rp_s2_rdy.eq(1)

                    with m.If(record.rs_data.rp_s3 == tag):
                        m.d.sync += record.rs_data.rp_s3_rdy.eq(1)
