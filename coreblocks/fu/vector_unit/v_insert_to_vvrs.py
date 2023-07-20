from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.structs_common.scoreboard import *

__all__ = ["VectorInsertToVVRS"]


class VectorInsertToVVRS(Elaboratable):
    """
    Module responsible for inserting instructions into the VVRS. It takes
    an instruction from the `VectorFrontend`, checks the readiness of its
    operands (with forward from the VVRS update method) and inserts them
    into the VVRS.

    Attributes
    ----------
    issue : Method
        Called to give the VVRS a new instruction to insert.
    update : Method
        The method to be called for each update in the VVRS.
    """

    def __init__(
        self,
        gen_params: GenParams,
        select: Method,
        insert: Method,
        scoreboard_get_list: list[Method],
        scoreboard_set: Method,
    ):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        select : Method
            The method to retrieve an empty register entry id from the VVRS.
        insert : Method
            Called to insert a new instruction into the VVRS.
        scoreboard_get_list : list[Method]
            Methods used to read the current state of readiness from the
            scoreboard.  It should contain at least 4 items.
        scoreboard_set : Method
            Used to mark a register as dirty.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.select = select
        self.insert = insert
        self.scoreboard_get_list = scoreboard_get_list
        self.scoreboard_set = scoreboard_set

        if len(self.scoreboard_get_list) < 4:
            raise ValueError("VectorInsertToVVRS need minimum 4 methods to read scoreboard.")

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.vvrs_layouts = VectorVRSLayout(self.gen_params, rs_entries_bits=self.gen_params.v_params.vvrs_entries_bits)
        self.issue = Method(i=self.layouts.vvrs_in)
        self.update = Method(i=self.vvrs_layouts.update_in)

    def elaborate(self, platform):
        m = TModule()

        currently_updated_reg = Record(self.gen_params.get(CommonLayouts).p_register_entry)

        @def_method(m, self.update)
        def _(tag, value):
            m.d.top_comb += currently_updated_reg.eq(tag)

        @def_method(m, self.issue)
        def _(arg):
            rs_entry_id = self.select(m)
            rs_data = Record(self.vvrs_layouts.data_layout)
            m.d.comb += assign(rs_data, arg)
            # check s1,s2,s3 registers
            for i, (rp, rp_rdy) in enumerate([(f"rp_{r}", f"rp_{r}_rdy") for r in ["s1", "s2", "s3"]]):
                with m.If((arg[rp].type == RegisterType.V) & ~(self.update.run & (arg[rp] == currently_updated_reg))):
                    cast_rp = Signal(self.v_params.vrp_count_bits)
                    m.d.top_comb += cast_rp.eq(arg[rp].id)
                    m.d.comb += rs_data[rp_rdy].eq(~self.scoreboard_get_list[i](m, id=cast_rp).dirty)
                with m.Else():
                    m.d.comb += rs_data[rp_rdy].eq(1)

            # check v0
            with m.If(self.update.run & (arg.rp_v0.id == currently_updated_reg.id)):
                m.d.comb += rs_data.rp_v0_rdy.eq(1)
            with m.Else():
                cast_v0 = Signal(self.v_params.vrp_count_bits)
                m.d.top_comb += cast_v0.eq(arg.rp_v0.id)
                m.d.comb += rs_data.rp_v0_rdy.eq(~self.scoreboard_get_list[3](m, id=cast_v0).dirty)

            # process rp_dst
            with m.If(arg.rp_dst.type == RegisterType.V):
                cast_rp_dst = Signal(self.v_params.vrp_count_bits)
                m.d.top_comb += cast_rp_dst.eq(arg.rp_dst.id)
                self.scoreboard_set(m, id=cast_rp_dst, dirty=1)
            insert_data = {"rs_entry_id": rs_entry_id, "rs_data": rs_data}
            self.insert(m, insert_data)

        return m
