from abc import ABC, abstractmethod
from dataclasses import dataclass

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coreblocks.params.genparams import GenParams
    from coreblocks.frontend.bpu.component import BPUComponent, FastPredictor, CfiPredictor, DirectionPredictor
    from coreblocks.frontend.bpu.micro_btb import MicroBTB

__all__ = [
    "BPUComponentConfig",
    "BPUPredictorConfig",
    "FastPredictorConfig",
    "CfiPredictorConfig",
    "DirectionPredictorConfig",
    "BranchPredictionConfig",
    "MicroBTBConfig",
    "RASConfig",
]


@dataclass(frozen=True)
class BPUComponentConfig(ABC):
    """Configuration for a BPU component."""

    def meta_width(self, fetch_width: int) -> int:
        """Bits of prediction metadata this component needs back for training."""
        return 0

    def validate(self) -> None:
        """Raise ValueError for invalid parameters."""


@dataclass(frozen=True)
class BPUPredictorConfig(BPUComponentConfig):
    """Configuration and factory for a predictor in the BPU pipeline."""

    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> "BPUComponent":
        raise NotImplementedError()


@dataclass(frozen=True)
class FastPredictorConfig(BPUPredictorConfig):
    """Configuration for the S1 fast predictor."""

    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> "FastPredictor":
        raise NotImplementedError()


@dataclass(frozen=True)
class CfiPredictorConfig(BPUPredictorConfig):
    """Configuration for a predictor providing CFI hints in S1 and targets in S2."""

    @abstractmethod
    def candidate_count(self) -> int:
        """Maximum CFI candidates per fetch block."""
        raise NotImplementedError()

    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> "CfiPredictor":
        raise NotImplementedError()


@dataclass(frozen=True)
class DirectionPredictorConfig(BPUPredictorConfig):
    """Configuration for the S2 direction predictor."""

    @abstractmethod
    def get_module(self, gen_params: "GenParams") -> "DirectionPredictor":
        raise NotImplementedError()


@dataclass(frozen=True)
class MicroBTBConfig(FastPredictorConfig):
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

    def get_module(self, gen_params: "GenParams") -> "MicroBTB":
        from coreblocks.frontend.bpu.micro_btb import MicroBTB

        return MicroBTB(gen_params, self)


@dataclass(frozen=True)
class RASConfig:
    """Configuration of the return address stack."""

    entries_log: int = 1
    """Log of the number of entries."""

    def validate(self):
        if self.entries_log < 1:
            raise ValueError("RAS must have at least 2 entries")


@dataclass(frozen=True)
class BranchPredictionConfig:
    """Configuration of the branch prediction unit and all of its sub-predictors."""

    ras: RASConfig = RASConfig()

    fast_predictor: FastPredictorConfig = MicroBTBConfig()

    def components(self) -> tuple[BPUPredictorConfig, ...]:
        return (self.fast_predictor,)

    def bpd_meta_width(self, fetch_width: int) -> int:
        return sum(component.meta_width(fetch_width) for component in self.components())

    def validate(self):
        self.ras.validate()
        for component in self.components():
            component.validate()
