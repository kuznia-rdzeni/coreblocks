from coreblocks.params.fu_params import DependencyKey, OutputKey
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.utils.protocols import Unifier


class WishboneDataKey(DependencyKey[WishboneMaster]):
    pass


class CommitOutputKey(OutputKey):
    @classmethod
    def unifier(cls) -> type[Unifier]:
        return MethodProduct

    @classmethod
    def method_name(cls) -> str:
        return "commit"


class BranchResultOutputKey(OutputKey):
    @classmethod
    def unifier(cls) -> type[Unifier]:
        return Collector

    @classmethod
    def method_name(cls) -> str:
        return "branch_result"
