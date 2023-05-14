from abc import abstractmethod, ABC
from typing import Iterable

from coreblocks.utils.protocols import FuncBlock, FuncUnit

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coreblocks.params.genparams import GenParams
    from coreblocks.params.optypes import OpType


__all__ = [
    "BlockComponentParams",
    "FunctionalComponentParams",
    "optypes_supported",
]


class BlockComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> FuncBlock:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set["OpType"]:
        raise NotImplementedError()


class FunctionalComponentParams(ABC):
    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> FuncUnit:
        raise NotImplementedError()

    @abstractmethod
    def get_optypes(self) -> set["OpType"]:
        raise NotImplementedError()


def optypes_supported(components: Iterable[BlockComponentParams | FunctionalComponentParams]) -> set["OpType"]:
    return {optype for component in components for optype in component.get_optypes()}
