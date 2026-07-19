from dataclasses import dataclass

__all__ = [
    "BranchPredictionConfig",
    "MicroBTBConfig",
]


@dataclass(frozen=True)
class MicroBTBConfig:
    """Configuration of the micro-BTB."""

    entries_log: int = 3
    """Log of the number of entries."""

    useful_cnt_width: int = 2
    """Width of the per-entry saturating usefulness counter that drives replacement."""

    def validate(self):
        if self.entries_log < 1:
            raise ValueError("Micro-BTB must have at least 2 entries")
        if self.useful_cnt_width < 1:
            raise ValueError("Micro-BTB usefulness counter must be at least 1 bit wide")


@dataclass(frozen=True)
class BranchPredictionConfig:
    """Configuration of the branch prediction unit and all of its sub-predictors."""

    micro_btb: MicroBTBConfig = MicroBTBConfig()

    def validate(self):
        self.micro_btb.validate()
