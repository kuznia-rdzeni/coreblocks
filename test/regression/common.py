from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from .memory import CoreMemoryModel
from transactron.profiler import Profile


@dataclass
class SimulationExecutionResult:
    """Information about the result of the simulation.

    Attributes
    ----------
    success: bool
        Whether the simulation finished successfully, i.e. no timeouts,
        no exceptions, no failed assertions etc.
    metric_values: dict[str, dict[str, int]]
        Values of the core metrics taken at the end of the simulation.
    """

    success: bool
    metric_values: dict[str, dict[str, int]] = field(default_factory=dict)
    profile: Optional[Profile] = None


class SimulationBackend(ABC):
    @abstractmethod
    async def run(self, mem_model: CoreMemoryModel, timeout_cycles: int) -> SimulationExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError
