from abc import ABC, abstractmethod

from .memory import CoreMemoryModel


class SimulationBackend(ABC):
    @abstractmethod
    async def run(self, mem_model: CoreMemoryModel, timeout_cycles: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError
