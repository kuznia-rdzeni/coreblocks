from coreblocks.params.fu_params import DependencyKey, MethodKey
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.utils.protocols import Unifier


class WishboneDataKey(DependencyKey[WishboneMaster]):
    pass


class CommitMethodKey(MethodKey):
    @classmethod
    def unifier(cls) -> type[Unifier]:
        return MethodProduct

    @classmethod
    def method_name(cls) -> str:
        return "commit"


class BranchResultMethodKey(MethodKey):
    @classmethod
    def unifier(cls) -> type[Unifier]:
        return Collector

    @classmethod
    def method_name(cls) -> str:
        return "branch_result"
