from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from amaranth import Elaboratable, Signal
from transactron import Method, TModule, def_method
from transactron.utils import assign, extend_layout
from coreblocks.params import GenParams
from coreblocks.interface.layouts import FuncUnitLayouts
from coreblocks.func_blocks.interface.func_protocols import FuncUnit
from coreblocks.func_blocks.fu.common.fu_decoder import DecoderManager


__all__ = ["FuncUnitBase"]


_T_DecoderManager = TypeVar("_T_DecoderManager", bound=DecoderManager)


class FuncUnitBase(ABC, FuncUnit, Elaboratable, Generic[_T_DecoderManager]):
    fn: _T_DecoderManager

    def __init__(self, gen_params: GenParams, fn: _T_DecoderManager):
        self.gen_params = gen_params
        self.layouts = gen_params.get(FuncUnitLayouts)
        self.issue = Method(i=self.layouts.issue)
        self.issue_decoded = Method(i=extend_layout(self.layouts.issue, ("decode_fn", fn.Fn)))
        self.push_result = Method(i=self.layouts.push_result)
        self.fn = fn

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.decoder = decoder = self.fn.get_decoder(self.gen_params)

        @def_method(m, self.issue)
        def _(arg):
            new_arg = Signal(self.issue_decoded.layout_in)
            m.d.av_comb += decoder.exec_fn.eq(arg.exec_fn)
            m.d.av_comb += assign(new_arg, arg)
            m.d.av_comb += new_arg.decode_fn.eq(decoder.decode_fn)
            self.issue_decoded(m, new_arg)

        return m
