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


def _remove_implications(extensions: Extension):
    implied_extensions = Extension(0)
    for ext in Extension:
        if ext in extensions and ext in extension_implications:
            implied_extensions |= extension_implications[ext]
    return extensions & ~implied_extensions


def extensions_supported(
    fu_config: Collection[BlockComponentParams], embedded: bool = False, compressed: bool = False
) -> tuple[Extension, Extension]:
    optypes = optypes_supported(fu_config)

    # Fully and partially supported extensions
    extensions_parital = Extension(0)
    # Fully supported extensions
    extensions_full = Extension(0)

    # OK: Add global switch if we want to use partial extensions with warning of unsupported ops (and default for now).
    # If not selected error if partial != full

    for ext in Extension:
        if ext.bit_count() != 1:  # don't process aliases, only extensions with unique id
            continue

        ext_added_optypes = optypes_required_by_extensions(ext, resolve_implications=False, ignore_unsupported=True)
        if ext_added_optypes & optypes:
            extensions_parital |= ext

        ext_all_optypes = optypes_required_by_extensions(ext, resolve_implications=True, ignore_unsupported=True)
        if optypes and ext_all_optypes and optypes.issuperset(ext_all_optypes):
            extensions_full |= ext

    # Needed for extensions that just imply others without adding new optypes (like B).
    # Adds them to partial extensions if they are fully supported for implied removal
    extensions_parital |= extensions_full

    # Remove implied extensions
    extensions_parital = _remove_implications(extensions_parital)
    extensions_full = _remove_implications(extensions_full)

    # Apply special extensions that can't be deduced from functional units

    if embedded:
        if Extension.I in extensions_parital:
            extensions_parital |= Extension.E
            extensions_parital ^= Extension.I
        if Extension.I in extensions_full:
            extensions_full |= Extension.E
            extensions_full ^= Extension.I

    if compressed:
        extensions_parital |= Extension.C
        extensions_full |= Extension.C

    return (extensions_parital, extensions_full)
