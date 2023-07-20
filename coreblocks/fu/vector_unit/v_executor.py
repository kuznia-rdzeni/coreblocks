from amaranth import *
from coreblocks.transactions import *
from coreblocks.transactions.lib import *
from coreblocks.utils import *
from coreblocks.params import *
from coreblocks.utils.fifo import *
from coreblocks.scheduler.wakeup_select import *
from coreblocks.fu.vector_unit.v_layouts import *
from coreblocks.fu.vector_unit.vrs import *
from coreblocks.fu.vector_unit.v_insert_to_vvrs import *
from coreblocks.structs_common.scoreboard import *
from coreblocks.fu.vector_unit.v_needed_regs import *
from coreblocks.fu.vector_unit.v_len_getter import *
from coreblocks.fu.vector_unit.v_elems_downloader import *
from coreblocks.fu.vector_unit.v_elems_uploader import *
from coreblocks.fu.vector_unit.v_mask_extractor import *
from coreblocks.fu.vector_unit.v_execution_ender import *
from coreblocks.fu.vector_unit.vector_alu import *
from coreblocks.fu.vector_unit.vrf import *
from coreblocks.fu.vector_unit.v_execution_data_spliter import *


class VectorExecutor(Elaboratable):
    """Module that executes vector instructions

    This module takes an instruction and executes it on its own part of the register file.
    First the required registers and their length are determined. Then there are initialised:
    - `VectorElemsDownloader`
    - `VectorExecutionDataSplitter`
    - `VectorElemsUploader`

    Data downloaded by the `VectorElemsDownloader` is passed to the `VectorExecutionDataSplitter`,
    which uses it to prepare data for `VectorBasicFlexibleAlu`, `VectorMaskExtractor`
    and `VectorElemsUploader`. The results of the vector alu calculation are passed to
    the `VectorElemsUploader` which sends them to the vector register.

    Attributes
    ----------
    issue : Method
        Used to pass a new instruction to process.
    initialise_regs : list[Method]
        A list of methods, one for each vector register, to initialise its
        content on vector register allocation.
    """

    def __init__(self, gen_params: GenParams, fragment_index: int, end: Method):
        """
        Parameters
        ----------
        gen_params : GenParams
            Core configuration.
        fragment_index : int
            Index of the executor. It has to fulfil:
            `0 <= fragment_index < register_bank_count`
        end : Method
            The method called to notify the `VectorExecutionEnder` that the execution has ended.
        """
        self.gen_params = gen_params
        self.v_params = self.gen_params.v_params
        self.fragment_index = fragment_index
        self.end = end

        self.layouts = VectorBackendLayouts(self.gen_params)
        self.alu_layouts = VectorAluLayouts(self.gen_params)
        self.vreg_layout = VectorRegisterBankLayouts(self.gen_params)

        self.issue = Method(i=self.layouts.executor_in)
        self.initialise_regs = [
            Method(i=self.vreg_layout.initialise, name=f"initialise{i}") for i in range(self.v_params.vrp_count)
        ]

    def elaborate(self, platform) -> TModule:
        m = TModule()
        end_pending_to_report = Signal()

        # TODO Check if it is worth moving needed_regs to backend so to don't have
        # unneeded copies, at the cost of pushing more data.
        needed_regs = VectorNeededRegs(self.gen_params)
        len_getter = VectorLenGetter(self.gen_params, self.fragment_index)

        vrf = VRFFragment(gen_params=self.gen_params)
        for i in range(self.v_params.vrp_count):
            self.initialise_regs[i].proxy(m, vrf.initialise_list[i])

        fu_in_fifo = BasicFifo(self.alu_layouts.alu_in, 2)
        mask_in_fifo = BasicFifo(self.layouts.mask_extractor_in, 2)
        old_dst_fifo = BasicFifo(self.layouts.uploader_old_dst_in, 4)
        fu_out_fifo = BasicFifo(self.layouts.fu_data_out, 2)
        mask_out_fifo = BasicFifo(self.layouts.mask_extractor_out, 2)

        splitter = VectorExecutionDataSplitter(
            self.gen_params, fu_in_fifo.write, old_dst_fifo.write, mask_in_fifo.write
        )
        downloader = VectorElemsDownloader(self.gen_params, vrf.read_req, vrf.read_resp, splitter.issue)
        uploader = VectorElemsUploader(self.gen_params, vrf.write, old_dst_fifo.read, mask_out_fifo.read, self.end)

        issue_connect = Connect(self.layouts.executor_in)
        self.issue.proxy(m, issue_connect.write)

        connect_input_data = Transaction(name="connect_input_data")
        with connect_input_data.body(m, request=~end_pending_to_report):
            instr = issue_connect.read(m)
            len_out = len_getter.issue(m, instr)
            needed_regs_out = needed_regs.issue(m, instr)
            downloader_in_data = Record(self.layouts.downloader_in)
            m.d.top_comb += assign(downloader_in_data, len_out, fields=AssignType.RHS)
            m.d.top_comb += assign(downloader_in_data, needed_regs_out, fields=AssignType.RHS)
            m.d.top_comb += [
                downloader_in_data.s1.eq(instr.rp_s1.id),
                downloader_in_data.s2.eq(instr.rp_s2.id),
                downloader_in_data.s3.eq(instr.rp_s3.id),
                downloader_in_data.v0.eq(instr.rp_v0.id),
            ]
            with m.If(len_out.elens_len != 0):
                # hot path
                downloader.issue(m, downloader_in_data)
                uploader.init(m, vrp_id=instr.rp_dst.id, ma=instr.vtype.ma, elens_len=len_out.elens_len)
                splitter.init(m, vtype=instr.vtype, exec_fn=instr.exec_fn, s1_val=instr.s1_val)
            with m.Else():
                # cold path
                m.d.sync += end_pending_to_report.eq(1)

        with Transaction(name="trans_end_pending_report").body(m, request=end_pending_to_report):
            m.d.sync += end_pending_to_report.eq(0)
            self.end(m)

        alu = VectorBasicFlexibleAlu(self.gen_params, fu_out_fifo.write)
        connect_alu_in = ConnectTrans(fu_in_fifo.read, alu.issue)
        connect_alu_out = ConnectTrans(fu_out_fifo.read, uploader.issue)

        mask_extractor = VectorMaskExtractor(self.gen_params, mask_out_fifo.write)
        connect_mask_extractor_in = ConnectTrans(mask_in_fifo.read, mask_extractor.issue)

        # Add everything to submodules
        m.submodules.needed_regs = needed_regs
        m.submodules.len_getter = len_getter
        m.submodules.vrf = vrf
        m.submodules.fu_in_fifo = fu_in_fifo
        m.submodules.mask_in_fifo = mask_in_fifo
        m.submodules.old_dst_fifo = old_dst_fifo
        m.submodules.fu_out_fifo = fu_out_fifo
        m.submodules.mask_out_fifo = mask_out_fifo
        m.submodules.splitter = splitter
        m.submodules.downloader = downloader
        m.submodules.uploader = uploader
        m.submodules.issue_connect = issue_connect
        m.submodules.alu = alu
        m.submodules.mask_extractor = mask_extractor
        m.submodules.connect_mask_extractor_in = connect_mask_extractor_in
        m.submodules.connect_alu_in = connect_alu_in
        m.submodules.connect_alu_out = connect_alu_out

        return m
