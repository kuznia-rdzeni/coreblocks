import os
import json
from pathlib import Path

from .memory import *
from .common import SimulationBackend

test_dir = Path(__file__).parent.parent
embench_dir = test_dir.joinpath("external/embench/build/src")
results_dir = test_dir.joinpath("regression/benchmark_results")


class MMIO(RandomAccessMemory):
    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(range(0x80000000, 0x80000000 + 24), SegmentFlags.READ | SegmentFlags.WRITE, b"\x00" * 24)
        self.on_finish = on_finish

    def write(self, req: WriteRequest) -> WriteReply:
        if req.addr == 0x0:
            self.on_finish()
            return WriteReply()
        else:
            return super().write(req)

    def return_code(self):
        return int.from_bytes(self.data[4:8], "little")

    def cycle_cnt(self):
        return int.from_bytes(self.data[8:16], "little")

    def instr_cnt(self):
        return int.from_bytes(self.data[16:24], "little")


def get_all_benchmark_names():
    return os.listdir(embench_dir)


async def run_benchmark(sim_backend: SimulationBackend, benchmark_name: str):
    mmio = MMIO(lambda: sim_backend.stop())

    mem_segments: list[MemorySegment] = []
    mem_segments += load_segments_from_elf(str(embench_dir.joinpath(f"{benchmark_name}/{benchmark_name}")))
    mem_segments.append(mmio)

    mem_model = CoreMemoryModel(mem_segments)

    success = await sim_backend.run(mem_model, timeout_cycles=5000000)

    if not success:
        raise RuntimeError("Simulation timed out")

    if mmio.return_code() != 0:
        raise RuntimeError("The benchmark exited with a non-zero return code: %d" % mmio.return_code())

    results = {"cycle": mmio.cycle_cnt(), "instr": mmio.instr_cnt()}

    os.makedirs(str(results_dir), exist_ok=True)
    with open(f"{str(results_dir)}/{benchmark_name}.json", "w") as outfile:
        json.dump(results, outfile)
