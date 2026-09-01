"""A simulation backend whose hot path lives entirely in C++."""

import importlib.util
import threading
from types import ModuleType
from typing import Callable, Optional

from .common import SimulationBackend, SimulationExecutionResult
from .cxx_build import MODULE_NAME, MODULE_PATH, ensure_cxxsim_built
from .memory import (
    CoreMemoryModel,
    MMIOSegment,
    RandomAccessMemory,
    ReadRequest,
    ReplyStatus,
    WriteRequest,
)

_native: Optional[ModuleType] = None
_native_lock = threading.Lock()


def load_native_module() -> ModuleType:
    global _native

    with _native_lock:
        if _native is None:
            if not MODULE_PATH.exists():
                ensure_cxxsim_built()

            spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _native = module

    return _native


class CxxSimulation(SimulationBackend):
    def __init__(self):
        self.sim = None

    def stop(self):
        if self.sim is not None:
            self.sim.request_stop()

    def _mmio_callbacks(self, native: ModuleType, segment: MMIOSegment, sim, get_interrupt_value):
        status_codes = {
            ReplyStatus.OK: native.ReplyStatus.OK,
            ReplyStatus.ERROR: native.ReplyStatus.ERROR,
            ReplyStatus.RETRY: native.ReplyStatus.RETRY,
        }

        def update_interrupts():
            if get_interrupt_value is not None:
                sim.set_interrupts(get_interrupt_value())

        def on_read(addr: int, byte_count: int, byte_sel: int, exec: bool):
            reply = segment.read(ReadRequest(addr=addr, byte_count=byte_count, byte_sel=byte_sel, exec=exec))
            update_interrupts()
            return status_codes[reply.status], reply.data

        def on_write(addr: int, data: int, byte_count: int, byte_sel: int):
            reply = segment.write(WriteRequest(addr=addr, data=data, byte_count=byte_count, byte_sel=byte_sel))
            update_interrupts()
            return status_codes[reply.status]

        return on_read, on_write

    async def run(
        self,
        mem_model: CoreMemoryModel,
        timeout_cycles: int = 5000,
        get_interrupt_value: Optional[Callable[[], int]] = None,
    ) -> SimulationExecutionResult:
        native = load_native_module()

        sim = native.Simulation(
            timeout_cycles=timeout_cycles,
            fail_on_undefined_read=mem_model.fail_on_undefined_read,
            fail_on_undefined_write=mem_model.fail_on_undefined_write,
        )

        for segment in mem_model.segments:
            start = segment.address_range.start
            end = segment.address_range.stop
            flags = int(segment.flags)

            match segment:
                case RandomAccessMemory():
                    sim.add_ram(start, end, flags, segment.contents)
                case MMIOSegment():
                    on_read, on_write = self._mmio_callbacks(native, segment, sim, get_interrupt_value)
                    sim.add_mmio(start, end, flags, on_read, on_write)
                case _:
                    raise RuntimeError(f"The cxxsim backend cannot realize {type(segment).__name__}")

        self.sim = sim
        try:
            result = sim.run()
        finally:
            self.sim = None

        return SimulationExecutionResult(
            success=result.reason == native.FinishReason.STOPPED, simulated_cycles=result.cycles
        )
