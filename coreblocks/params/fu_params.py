from abc import abstractmethod, ABC
from typing import Iterable

from coreblocks.utils.protocols import FuncBlock, FuncUnit
from coreblocks.params.isa import Extension, extension_implications
from coreblocks.params.optypes import optypes_required_by_extensions

from typing import TYPE_CHECKING, Collection


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


def optypes_supported(block_components: Iterable[BlockComponentParams]) -> set["OpType"]:
    return {optype for block in block_components for optype in block.get_optypes()}


def _remove_implications(extensions: set[Extension]):
    implied_extensions = set()
    for ext in extensions:
        if ext in extension_implications:
            implied_extensions |= extension_implications[ext]
    return extensions - implied_extensions


## Move that to genparams?
def extensions_supported(fu_config: Collection[BlockComponentParams]) -> tuple[set[Extension], set[Extension]]:
    optypes = optypes_supported(fu_config)

    # Fully and partially supported extensions
    extensions_parital: set[Extension] = set()
    # Fully supported extensions
    extensions_full: set[Extension] = set()

    # OK: Add global switch if we want to use partial extensions with warning of unsupported ops (and default for now). If not selected error if partial != full

    for ext in Extension:
        ext_added_optypes = optypes_required_by_extensions({ext}, resolve_implications=False, ignore_unsupported=True)
        if ext_added_optypes & optypes:
            extensions_parital.add(ext)

        ext_all_optypes = optypes_required_by_extensions({ext}, resolve_implications=True, ignore_unsupported=True)
        if optypes and ext_all_optypes and optypes.issuperset(ext_all_optypes):
            extensions_full.add(ext)

    # needed for extensions that just imply others without adding new optypes (like B).
    # add them to partial extensions if they are fully supported for implied removal
    extensions_parital |= extensions_full

    # remove implied extensions
    extensions_parital = _remove_implications(extensions_parital)
    extensions_full = _remove_implications(extensions_full)

    # special modifications

    # TODO: convert to G; E->I (if gp); ISA STR ORDER MATTERS

    #: generate isa strings in another function (isa_str, compiler_isa_str (bypass for zmull), extra info (with partial/full info and machine/sup mode)

    print(extensions_parital, extensions_full)

    return (extensions_parital, extensions_full)
