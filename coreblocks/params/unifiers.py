from coreblocks.transactions.lib import MethodProduct, Collector
from coreblocks.utils.protocols import Unifier


blocks_method_unifiers: dict[str, type[Unifier]] = {
    "commit": MethodProduct,
    "branch_result": Collector,
}
