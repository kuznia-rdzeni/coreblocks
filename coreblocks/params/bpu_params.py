from dataclasses import dataclass

__all__ = [
    "BranchPredictionConfig",
]


@dataclass(frozen=True)
class BranchPredictionConfig:
    """Configuration of the branch prediction unit and all of its sub-predictors."""

    # micro-BTB
    ubtb_entries_log: int = 5
    """Log of the number of micro-BTB entries."""

    ubtb_useful_cnt_width: int = 2
    """Width of the per-entry saturating usefulness counter that drives micro-BTB replacement."""

    # return address stack
    ras_entries_log: int = 4
    """Log of the number of return address stack entries."""
