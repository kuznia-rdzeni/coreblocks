from glob import glob
from pathlib import Path

from .memory import *
from .common import SimulationBackend

test_dir = Path(__file__).parent.parent
riscv_tests_dir = test_dir.joinpath("external/riscv-tests")


class MMIO(MemorySegment):
    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(range(0x80000000, 0x80000000 + 4), SegmentFlags.READ | SegmentFlags.WRITE)
        self.on_finish = on_finish
        self.failed_test = 0

    def read(self, req: ReadRequest) -> ReadReply:
        return ReadReply()

    def write(self, req: WriteRequest) -> WriteReply:
        self.failed_test = req.data
        self.on_finish()
        return WriteReply()


def get_all_test_names():
    return {name[5:] for name in glob("test-*", root_dir=riscv_tests_dir)}


async def run_test(sim_backend: SimulationBackend, test_name: str):
    mmio = MMIO(lambda: sim_backend.stop())

    mem_segments: list[MemorySegment] = []
    mem_segments += load_segments_from_elf(str(riscv_tests_dir.joinpath("test-" + test_name)))
    mem_segments.append(mmio)

    mem_model = CoreMemoryModel(mem_segments)

    success = await sim_backend.run(mem_model)

    if not success:
        raise RuntimeError("Simulation timed out")

    if mmio.failed_test:
        raise RuntimeError("Failing test: %d" % mmio.failed_test)
