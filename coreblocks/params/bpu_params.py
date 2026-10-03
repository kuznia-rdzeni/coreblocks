from abc import ABC, abstractmethod
from dataclasses import dataclass

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from coreblocks.params.genparams import GenParams
    from coreblocks.frontend.bpu.component import BPUComponent, FastPredictor, CfiPredictor, DirectionPredictor
    from coreblocks.frontend.bpu.micro_btb import MicroBTB
    from coreblocks.frontend.bpu.main_btb import MainBTB
    from coreblocks.frontend.bpu.bimodal import Bimodal

__all__ = [
    "BPUComponentConfig",
    "BPUPredictorConfig",
    "FastPredictorConfig",
    "CfiPredictorConfig",
    "DirectionPredictorConfig",
    "BranchPredictionConfig",
    "MicroBTBConfig",
    "RASConfig",
    "MainBTBConfig",
    "BimodalConfig",
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
class MainBTBConfig(CfiPredictorConfig):
    """Configuration of the main BTB."""

    sets_log: int = 6
    """Log of the number of sets."""

    ways: int = 4
    """Number of ways in a set. A way holds a single CFI, so this is also the maximum
    number of CFIs of one fetch block that the BTB can predict."""

    tag_width: int = 16
    """Width of the stored tag. Tags narrower than the fetch block address make different
    blocks alias onto the same entry."""

    target_width: int = 20
    """Number of the target's low bits stored in an entry, counted in the minimal
    instruction width. The remaining high bits are reconstructed from the fetch block
    address and a two-bit carry."""

    def meta_width(self, fetch_width: int) -> int:
        from coreblocks.arch import CfiType

        position_width = (fetch_width - 1).bit_length()
        return self.ways * (2 + position_width + CfiType.as_shape().width)

    def candidate_count(self) -> int:
        return self.ways

    def validate(self):
        if self.sets_log < 1:
            raise ValueError("Main BTB must have at least 2 sets")
        if self.ways < 2 or self.ways & (self.ways - 1) != 0:
            raise ValueError("Main BTB way count must be a power of two, at least 2")
        if self.tag_width < 1:
            raise ValueError("Main BTB tag must be at least 1 bit wide")
        if self.target_width < 1:
            raise ValueError("Main BTB target must be at least 1 bit wide")

    def get_module(self, gen_params: "GenParams") -> "MainBTB":
        from coreblocks.frontend.bpu.main_btb import MainBTB

        return MainBTB(gen_params, self)


@dataclass(frozen=True)
class BimodalConfig(DirectionPredictorConfig):
    """Configuration of the position-indexed bimodal direction predictor."""

    sets_log: int = 8
    """Log of the number of table rows."""

    counter_width: int = 2
    """Width of each saturating direction counter."""

    def meta_width(self, fetch_width: int) -> int:
        return fetch_width * self.counter_width

    def validate(self):
        if self.sets_log < 1:
            raise ValueError("Bimodal predictor must have at least 2 sets")
        if self.counter_width < 2:
            raise ValueError("Bimodal counters must be at least 2 bits wide")

    def get_module(self, gen_params: "GenParams") -> "Bimodal":
        from coreblocks.frontend.bpu.bimodal import Bimodal

        return Bimodal(gen_params, self)


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
    cfi_predictor: CfiPredictorConfig | None = None
    direction_predictor: DirectionPredictorConfig | None = None

    def components(self) -> tuple[BPUPredictorConfig, ...]:
        return tuple(
            component
            for component in (
                self.fast_predictor,
                self.cfi_predictor,
                self.direction_predictor,
            )
            if component is not None
        )

    def bpd_meta_width(self, fetch_width: int) -> int:
        return sum(component.meta_width(fetch_width) for component in self.components())

    def validate(self):
        self.ras.validate()

        if (self.cfi_predictor is None) != (self.direction_predictor is None):
            raise ValueError("CFI and direction predictors must either both be configured or both be omitted")

        for component in self.components():
            component.validate()
