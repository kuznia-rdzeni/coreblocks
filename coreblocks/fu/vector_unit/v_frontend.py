from typing import Optional
from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.utils import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.fu.vector_unit.v_input_verification import *
from coreblocks.fu.vector_unit.v_status import *
from coreblocks.fu.vector_unit.v_translator import *
from coreblocks.fu.vector_unit.v_alloc_rename import *

__all__ = ["VectorFrontend"]

class VectorMemoryVVRSSplitter(Elaboratable):
    def __init__(self, gen_params : GenParams, v_params : VectorParameters, put_to_mem : Method, put_to_vvrs : Method):
        self.gen_params = gen_params
        self.v_params = v_params
        self.put_to_mem = put_to_mem
        self.put_to_vvrs = put_to_vvrs

        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.issue = Method(i = self.layouts.alloc_rename_out)

    def elaborate(self, platform) -> TModule:
        m = TModule()

        @def_method(m, self.issue)
        def _(arg):
            with m.If(arg.exec_fn.op_type == OpType.V_MEMORY):
                rec_mem = Record(self.layouts.instr_to_mem)
                m.d.top_comb += assign(rec_mem, arg, fields = AssignType.COMMON)
                self.put_to_mem(m, rec_mem)
            with m.Else():
                rec_vvrs = Record(self.layouts.instr_to_vvrs)
                m.d.top_comb += assign(rec_vvrs, arg, fields = AssignType.COMMON)
                self.put_to_vvrs(m, rec_vvrs)
        return m


class VectorFrontend(Elaboratable):

    def __init__(self, gen_params : GenParams, v_params : VectorParameters, rob_block_interrupts : Method, retire : Method, retire_mult : Method, alloc_reg : Method,
                 get_rename1_frat : Method, get_rename2_frat : Method, set_rename_frat : Method, put_to_mem : Method, put_to_vvrs : Method):
        self.gen_params = gen_params
        self.v_params = v_params
        self.layouts = VectorFrontendLayouts(self.gen_params, self.v_params)
        self.rob_block_interrupts = rob_block_interrupts
        #TODO Prepare more retire methods to use in different places
        self.retire = retire
        self.retire_mult = retire_mult
        self.alloc_reg = alloc_reg
        self.get_rename1_frat = get_rename1_frat
        self.get_rename2_frat = get_rename2_frat
        self.set_rename_frat = set_rename_frat
        self.put_to_mem = put_to_mem
        self.put_to_vvrs = put_to_vvrs

        self.vxrs_layouts = VectorXRSLayout(self.gen_params, rs_entries_bits = log2_int(self.v_params.vxrs_entries, False))
        self.insert = Method(i = self.vxrs_layouts.insert_in)
        self.select = Method(o = self.vxrs_layouts.select_out)
        self.update = Method(i = self.vxrs_layouts.update_in)

    def elaborate(self, platform) -> TModule:
        m = TModule()


        m.submodules.fifo_from_v_status = fifo_from_v_status = BasicFifo(self.layouts.status_out, 2)
        m.submodules.v_status = v_status = VectorStatusUnit(self.gen_params, self.v_params, fifo_from_v_status.write, self.retire)
        m.submodules.verificator = verificator = VectorInputVerificator(self.gen_params, self.v_params, self.rob_block_interrupts, v_status.issue, v_status.get_vill, v_status.get_vstart, self.retire)

        m.submodules.vxrs = vxrs = VXRS(self.gen_params, self.v_params.vxrs_entries)
        self.insert.proxy(m, vxrs.insert)
        self.select.proxy(m, vxrs.select)
        self.update.proxy(m, vxrs.update)
        m.submodules.wakeup_xrs = wakeup_xrs = WakeupSelect(gen_params = self.gen_params, get_ready = vxrs.get_ready_list[0],take_row = vxrs.take, issue= verificator.issue, row_layout = self.layouts.verification_in)

        
        m.submodules.fifo_from_translator = fifo_from_translator = BasicFifo(self.layouts.translator_out, 2)
        m.submodules.translator = translator = VectorTranslator(self.gen_params, self.v_params, fifo_from_translator.write, self.retire_mult)

        m.submodules.from_status_to_tranlator = ConnectTrans(fifo_from_v_status.read, translator.issue)
        
        m.submodules.alloc_rename = alloc_rename = VectorAllocRename(self.gen_params, self.v_params, self.alloc_reg, self.get_rename1_frat, self.get_rename2_frat, self.set_rename_frat)
        m.submodules.splitter = splitter = VectorMemoryVVRSSplitter(self.gen_params, self.v_params, self.put_to_mem, self.put_to_vvrs)
        
        with Transaction(name="allocating").body(m):
            instr = fifo_from_translator.read(m)
            renamed = alloc_rename.issue(m, instr)
            splitter.issue(m, renamed)


        return m
