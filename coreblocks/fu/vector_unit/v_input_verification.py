# Zweryfikować czy wspieramy dane SEW i LMUL, czyli:
#   - SEW <= ELEN
#   - LMUL >= 8/ELEN
# Jeśli nie to ustawić vill

# Jeśli wykonujemy instrukcję i `vill` jest ustawiony, to zgłaszamy wyjątek `illegal instruction`
#   - dotyczy tylko instrukcji używających vtype, czyli wszystkich poza vsetvl, loadami storami i movami
#
# Jeśli vill jest 1, to wszystkie pozostałe bity z rejestru powinny być 0
#
# - Każda instrukcja resetuje vstart
# - vstart jest zapisywany przede wszystkim przez HW podczas przerwania/wyjątku
# - vstart is not modi ed by vector instructions that raise illegal-instruction exceptions.
# - The vstart CSR is writable by unprivileged code, but non-zero vstart values may cause vector instructions to run
#   substantially slower on some implementations, so vstart should not be used by application programmers
# - Implementations are permitted to raise illegal instruction exceptions when attempting to execute a vector instruction with a
#   value of vstart that the implementation can never produce when executing that same instruction with the same vtype
#   setting.
#
# It is recommended that at reset, vtype.vill is set, the remaining bits in vtype are zero, and vl is set to zero.
#
# Jeśli mamy grupę rejestrów to powinna być ona odpowiednio wyrównana - zarezerwowane
# poszerzanie dla LMUL8 i zwężanie dla minimalnego LMUL są zarezerowowane
#
# podniesienie wyjątku powinno blokować dalsze przetwarzanie?
#
# When vstart ≥ vl, there are no body elements, and no elements are updated in any destination vector register group,
# including that no tail elements are updated with agnostic values. - trzeba zrobić tylko renaming

from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.params import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.utils.fifo import BasicFifo

class VectorInputVerificator(Elaboratable):
    def __init__(self, gen_params : GenParams, v_params : VectorParameters, rob_block_interrupts : Method, put_instr : Method, get_vill : Method, get_vstart : Method, retire : Method):
        self.gen_params = gen_params
        self.v_params = v_params
        self.rob_block_interrupts = rob_block_interrupts
        self.put_instr = put_instr
        self.get_vill = get_vill
        self.get_vstart = get_vstart
        self.retire = retire

        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.vill = Signal()
        self.vstart = Signal(self.v_params.vstart_bits)
        self.dependency_manager = self.gen_params.get(DependencyManager)
        self.report = self.dependency_manager.get_dependency(ExceptionReportKey())

        self.issue = Method(i=self.layouts.verification_in)
        self.clear = Method()

    def check_instr(self, m : TModule, instr) -> Value:
        # TODO add checking if instruction is whole-register move, load or store (so they don't use vtype)
        illegal_because_vill = Signal()
        with m.If((self.vill == 1) & (instr.exec_fn.op_type != OpType.V_CONTROL)):
            m.d.comb += illegal_because_vill.eq(1)

        # TODO add checking for specific instructions that support not zero start
        # as for now we assume that no instruction can be stopped inside of execution
        # (which is not true, because of load/stores)
        illegal_because_vstart = Signal()
        with m.If(self.vstart !=0):
            m.d.comb += illegal_because_vstart.eq(1)

        return illegal_because_vill | illegal_because_vstart

    def elaborate(self, platform):
        m = TModule()

        fifo = BasicFifo(self.layouts.verification_in, 2)
        m.submodules.fifo = fifo

        self.issue.proxy(m, fifo.write)

        raise_illegal = Signal()
        m.d.top_comb += raise_illegal.eq(self.check_instr(m, fifo.head))

        with Transaction(name = "verify").body(m):
            instr = fifo.read(m)
            with condition(m, nonblocking = False) as branch:
                with branch(raise_illegal == 0):
                    self.put_instr(m, instr)
                    self.rob_block_interrupts(m, rob_id = instr.rob_id)
                with branch(raise_illegal == 1):
                    self.report(m, rob_id = instr.rob_id, cause = ExceptionCause.ILLEGAL_INSTRUCTION)
                    self.retire(m, rob_id = instr.rob_id, exception = 1, rp_dst = instr.rp_dst, result = 0)
        with Transaction(name = "getters").body(m):
            m.d.comb += self.vstart.eq(self.get_vstart(m).vstart)
            m.d.comb += self.vill.eq(self.get_vill(m).vill)

        @def_method(m, self.clear)
        def _():
            fifo.clear(m)

        return m
