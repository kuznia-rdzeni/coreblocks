from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from amaranth import Elaboratable
from transactron import Method, TModule
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
        self.push_result = Method(i=self.layouts.push_result)
        self.fn = fn
        self.decoder = fn.get_decoder(gen_params)

    @abstractmethod
    def elaborate(self, platform) -> TModule:
        m = TModule()

        m.submodules.decoder = self.decoder

        return m
