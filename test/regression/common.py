from abc import ABC, abstractmethod

from .memory import CoreMemoryModel


class SimulationBackend(ABC):
    @abstractmethod
    async def run(self, mem_model: CoreMemoryModel) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stop(self):
        raise NotImplementedError
