from typing import Protocol

from transactron import Method

from transactron.utils._typing import HasElaborate

__all__ = ["BranchPredictionUnitInterface"]


class BranchPredictionUnitInterface(HasElaborate, Protocol):
    """
    Branch Prediction Unit Interface.

    """

    request: Method
    read_target_pred: Method
    read_pred_details: Method
    update: Method
    flush: Method
