from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.utils import load_store_width_to_eew
from coreblocks.utils.fifo import BasicFifo

__all__ = ["VectorInputVerificator"]


class VectorInputVerificator(Elaboratable):
    """Module to verify incoming vector instructions

    This module should check if incoming vector instructions are correct,
    if not, it raises an ILLEGAL_INSTRUCTION exception and immediately
    retire instruction. It currently checks:
    - if vtype dependent instruction doesn't come when `vill` is set
    - if vstart has a supported value (currently only vstart=0 is supported)
    Retiring illegal instructions immediately skips all steps in the middle of the
    vector pipeline. Notably, such instructions aren't passed to VectorStatusUnit
    so vstart isn't updated. This is a behaviour as required by the specification.

    There are no checks if instruction is being reserved and the behaviour is
    unspecified (as RISC-V allows).

    Attributes
    ----------
    issue : Method
        Called to insert a new instruction to process.
        Layout: VectorFrontendLayouts.verification_in
    clear : Method
        Clear internal state.
    """

    def __init__(
        self,
        gen_params: GenParams,
        rob_block_interrupts: Method,
        put_instr: Method,
        get_vill: Method,
        get_vstart: Method,
        retire: Method,
    ):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        rob_block_interrupts : Method
            Method to be called to block interrupts on the given rob_id.
        put_instr : Method
            Method used to pass vector instructions that operate on data to the next pipeline stage.
            Layout: VectorFrontendLayouts.verification_out
        get_vill : Method
            Method used to get the current (in terms of programme order) vill. Care
            should be taken to avoid introducing erroneous latency.
        get_vstart : Method
            Method used to get the current (in terms of programme order) vstart. Care
            should be taken to avoid introducing erroneuos latency.
        retire : Method
            Method used to inform about the retirement of vset{i}vl{i} instructions.
            Layout: FuncUnitLayouts.accept
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.rob_block_interrupts = rob_block_interrupts
        self.put_instr = put_instr
        self.get_vill = get_vill
        self.get_vstart = get_vstart
        self.retire = retire

        self.layouts = VectorFrontendLayouts(self.gen_params)
        self.vill = Signal()
        self.vstart = Signal(self.v_params.vstart_bits)
        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.issue = Method(i=self.layouts.verification_in)
        self.clear = Method()

    def check_instr(self, m: TModule, instr) -> Value:
        # TODO add checking if instruction is whole-register move, load or store (so they don't use vtype)
        illegal_because_vill = Signal()
        with m.If((self.vill == 1) & (instr.exec_fn.op_type != OpType.V_CONTROL)):
            m.d.comb += illegal_because_vill.eq(1)

        # TODO add checking for specific instructions that support not zero start
        # as for now we assume that no instruction can be stopped inside of execution
        # (which is not true, because of load/stores)
        illegal_because_vstart = Signal()
        with m.If(self.vstart != 0):
            m.d.comb += illegal_because_vstart.eq(1)

        illegal_because_LS_width = Signal()
        with m.If((load_store_width_to_eew(m, instr.exec_fn.funct3) > bits_to_eew(self.v_params.elen)) &
                  ( (instr.exec_fn.op_type == OpType.V_LOAD) | (instr.exec_fn.op_type == OpType.V_STORE))):
            m.d.comb += illegal_because_LS_width.eq(1)
        return illegal_because_vill | illegal_because_vstart | illegal_because_LS_width

    def elaborate(self, platform):
        m = TModule()

        fifo = BasicFifo(self.layouts.verification_in, 2)
        m.submodules.fifo = fifo

        self.issue.proxy(m, fifo.write)

        raise_illegal = Signal()
        m.d.top_comb += raise_illegal.eq(self.check_instr(m, fifo.head))

        with Transaction(name="verify").body(m):
            instr = fifo.read(m)
            with condition(m, nonblocking=False) as branch:
                with branch(raise_illegal == 0):
                    self.put_instr(m, instr)
                    self.rob_block_interrupts(m, rob_id=instr.rob_id)
                with branch(raise_illegal == 1):
                    self.report(m, rob_id=instr.rob_id, cause=ExceptionCause.ILLEGAL_INSTRUCTION)
                    self.retire(m, rob_id=instr.rob_id, exception=1, rp_dst=instr.rp_dst, result=0)
        with Transaction(name="getters").body(m):
            m.d.comb += self.vstart.eq(self.get_vstart(m).vstart)
            m.d.comb += self.vill.eq(self.get_vill(m).vill)

        @def_method(m, self.clear)
        def _():
            fifo.clear(m)

        return m
