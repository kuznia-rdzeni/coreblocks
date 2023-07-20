from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import *

__all__ = ["VectorExecutionEnder"]


class VectorExecutionEnder(Elaboratable):
    """Module to coordinate the end of execution of all `VectorExecutor`\\s

    Each `VectorExecutor` can end its work at a different time, so this
    module is responsible for coordinating this and terminating the instruction
    when all executors have finished their work.

    As part of terminating, the following actions are performed:
    - clearing the dirty bit in the vector register scoreboard
    - updating the rediness in the VVRS
    - announcing the end to the `VectorAnnouncer`
    - passing information about the end to the `VectorRetirement`

    Attributes
    ----------
    init : Method
        Called before the executors start working to initialise internal data.
    end_list : list[Method]
        List of methods for each executor to report that it has
        finished its work.
    """

    def __init__(
        self, gen_params: GenParams, announce: Method, update_vvrs: Method, scoreboard_set: Method, report_end: Method
    ):
        """
        Paramters
        ---------
        gen_params : GenParams
            Core configuration.
        announce : Method
            The method to notify the `VectorAnnouncer` that execution has ended.
        update_vvrs : Method
            Called to update the rediness of the vector operands in the VVRS.
        scoreboard_set : Method
            Used to clear the dirty bit in the vector register readinnes scoreboard.
        report_end : Method
            Forwards data about completed instruction to the `VectorRetirement`.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.announce = announce
        self.update_vvrs = update_vvrs
        self.scoreboard_set = scoreboard_set
        self.report_end = report_end

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.init = Method(i=self.layouts.ender_init_in)
        self.end_list = [Method() for _ in range(self.v_params.register_bank_count)]
        self.report_mult = Method(i=self.layouts.ender_report_mult)

    def elaborate(self, platform):
        m = TModule()

        rp_dst_saved = Record(self.gen_params.get(CommonLayouts).p_register_entry)
        rob_id_saved = Signal(self.gen_params.rob_entries_bits)
        valid = Signal()
        bank_ended = Signal(self.v_params.register_bank_count)

        end_transaction = Transaction()
        end_transaction.schedule_before(self.init)
        with end_transaction.body(m, request=bank_ended.all()):
            self.announce(m, exception=0, result=0, rob_id=rob_id_saved, rp_dst=rp_dst_saved)
            m.d.sync += valid.eq(0)
            m.d.sync += bank_ended.eq(0)
            with m.If(rp_dst_saved.type == RegisterType.V):
                cast_rp_dst = Signal(self.v_params.vrp_count_bits)
                m.d.top_comb += cast_rp_dst.eq(rp_dst_saved.id)
                self.scoreboard_set(m, id=cast_rp_dst, dirty=0)
                self.update_vvrs(m, tag=rp_dst_saved, value=0)
                self.report_end(m, rp_dst=rp_dst_saved, rob_id=rob_id_saved)

        @loop_def_method(m, self.end_list, ready_list=lambda _: valid)
        def _(i):
            m.d.sync += bank_ended[i].eq(1)

        @def_method(m, self.init, ready=~valid | end_transaction.grant)
        def _(rp_dst, rob_id):
            m.d.sync += rp_dst_saved.eq(rp_dst)
            m.d.sync += rob_id_saved.eq(rob_id)
            m.d.sync += valid.eq(1)

        # No support for LMUL!=1 yet
        @def_method(m, self.report_mult)
        def _(arg):
            pass

        return m
