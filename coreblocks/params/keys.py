from coreblocks.params.fu_params import DependencyKey, OutputKey
from coreblocks.peripherals.wishbone import WishboneMaster
from coreblocks.transactions.lib import MethodProduct, Collector


class WishboneDataKey(DependencyKey[WishboneMaster]):
    pass


class CommitOutputKey(OutputKey):
    unifier = MethodProduct
    method_name = "commit"


class BranchResultOutputKey(OutputKey):
    unifier = Collector
    method_name = "branch_result"
