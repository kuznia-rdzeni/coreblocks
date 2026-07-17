import os
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from pathlib import Path

from .memory import *
from .common import SimulationBackend

from coreblocks.arch import ExceptionCause

test_dir = Path(__file__).parent.parent
embench_dir = test_dir.joinpath("external/embench/build/src")
results_dir = test_dir.joinpath("regression/benchmark_results")
profile_dir = test_dir.joinpath("__profiles__")
evlog_dir = test_dir.joinpath("__evlogs__")


@dataclass_json
@dataclass
class BenchmarkResult:
    """Result of running a single benchmark.

    Attributes
    ----------
    cycles: int
        A number of cycles the benchmark took.
    instr: int
        A count of instructions commited during the benchmark.
    mispredicts: int
        A count of branch mispredictions during the benchmark, from the HPM counter.
    metric_values: dict[str, dict[str, int]]
        Values of the core metrics taken at the end of the simulation.
    """

    cycles: int
    instr: int
    mispredicts: int
    metric_values: dict[str, dict[str, int]]


class MMIO(RandomAccessMemory):
    """Memory Mapped IO.

    The structure of the MMIO is as follows:
    0x80000000-0x80000004 (int): finish signal - if the program writes here, the simulation terminates.
    0x80000004-0x80000008 (int): return code of the program
    0x80000008-0x8000000c (uintptr_t): mcause, if an exception occured
    0x8000000c-0x80000010 (uintptr_t): mepc, if an exception occured
    0x80000010-... (uint64_t each): benchmark counters, mirroring the `to_host` struct
        in the embench board support: cycles, instructions, branch mispredictions.
    """

    SIZE = 64  # leaves room for future counters
    COUNTERS_OFFSET = 0x10

    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(
            range(0x80000000, 0x80000000 + MMIO.SIZE), SegmentFlags.READ | SegmentFlags.WRITE, b"\x00" * MMIO.SIZE
        )
        self.on_finish = on_finish

    def write(self, req: WriteRequest) -> WriteReply:
        if req.addr == 0x0:
            self.on_finish()
            return WriteReply()
        else:
            return super().write(req)

    def _counter(self, index: int) -> int:
        offset = MMIO.COUNTERS_OFFSET + 8 * index
        return int.from_bytes(self.data[offset : offset + 8], "little")

    def return_code(self):
        return int.from_bytes(self.data[4:8], "little", signed=True)

    def mcause(self):
        return int.from_bytes(self.data[8:12], "little")

    def mepc(self):
        return int.from_bytes(self.data[12:16], "little")

    def cycle_cnt(self):
        return self._counter(0)

    def instr_cnt(self):
        return self._counter(1)

    def mispredict_cnt(self):
        return self._counter(2)


def get_all_benchmark_names():
    return os.listdir(embench_dir) if os.path.exists(embench_dir) else []


async def run_benchmark(sim_backend: SimulationBackend, benchmark_name: str):
    mmio = MMIO(lambda: sim_backend.stop())

    mem_segments: list[MemorySegment] = []
    mem_segments += load_segments_from_elf(str(embench_dir.joinpath(f"{benchmark_name}/{benchmark_name}")))
    mem_segments.append(mmio)

    mem_model = CoreMemoryModel(mem_segments)

    result = await sim_backend.run(mem_model, timeout_cycles=2000000)

    if result.profile is not None:
        os.makedirs(profile_dir, exist_ok=True)
        result.profile.encode(f"{profile_dir}/benchmark.{benchmark_name}.json")

    if result.evlog is not None:
        os.makedirs(evlog_dir, exist_ok=True)
        result.evlog.save(f"{evlog_dir}/benchmark.{benchmark_name}.jsonl")

    if not result.success:
        raise RuntimeError("Simulation timed out")

    if mmio.return_code() == -1:
        cause = ExceptionCause(mmio.mcause())
        raise RuntimeError(
            f"An exception was thrown while executing the benchmark. mcause: {cause.name}, mepc: 0x{mmio.mepc():x}"
        )

    if mmio.return_code() != 0:
        raise RuntimeError("The benchmark exited with a non-zero return code: %d" % mmio.return_code())

    bench_results = BenchmarkResult(
        cycles=mmio.cycle_cnt(),
        instr=mmio.instr_cnt(),
        mispredicts=mmio.mispredict_cnt(),
        metric_values=result.metric_values,
    )

    os.makedirs(str(results_dir), exist_ok=True)
    with open(f"{str(results_dir)}/{benchmark_name}.json", "w") as outfile:
        outfile.write(bench_results.to_json())  # type: ignore
