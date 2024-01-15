from .memory import *
from .common import SimulationBackend


class ToHostMMIO(MemorySegment):
    def __init__(self, addr: range, on_finish: Callable[[], None]):
        super().__init__(addr, SegmentFlags.READ | SegmentFlags.WRITE)
        self.on_finish = on_finish

    def read(self, _) -> ReadReply:
        return ReadReply()

    def write(self, _) -> WriteReply:
        self.on_finish()
        return WriteReply()


def map_mem_segments(
    elf_path: str, stop_callback: Callable[[], None]
) -> tuple[list[MemorySegment], RandomAccessMemory]:
    mem_segments = []
    signature_ram = RandomAccessMemory(range(0, 0), SegmentFlags.WRITE, bytearray())

    with open(elf_path, "rb") as f:
        elffile = ELFFile(f)

        signature_section = elffile.get_section(elffile.get_section_index(".signature"))
        tohost_section = elffile.get_section(elffile.get_section_index(".hostmmio"))

        for segment in elffile.iter_segments():
            # .signature and .tohost sections have direct segment mapping
            addr_range = range(segment.header["p_vaddr"], segment.header["p_vaddr"] + segment.header["p_memsz"])
            if segment.section_in_segment(signature_section):
                signature_ram = load_segment(segment)
            elif segment.section_in_segment(tohost_section):
                mem_segments.append(ToHostMMIO(addr_range, stop_callback))
            elif segment.header["p_type"] == "PT_LOAD":
                mem_segments.append(load_segment(segment))

    return (mem_segments, signature_ram)


async def run_test(sim_backend: SimulationBackend, test_path: str, signature_path: str):
    (mem_segments, signature_ram) = map_mem_segments(test_path, sim_backend.stop)

    mem_segments.append(signature_ram)
    mem_model = CoreMemoryModel(mem_segments)

    success = await sim_backend.run(mem_model, timeout_cycles=2000000)

    if not success:
        raise RuntimeError(f"{test_path}: Simulation timed out")

    print(f"{test_path}: Program execution finished! Signature: {signature_path}")

    # generate signature file in riscv-torture format (used also by riscof)
    # 32-bit little endian memory dump from data between .begin_signature and .end_signature
    # symbols, mapped to .signature section in our linker script
    with open(signature_path, "w") as sig_file:
        data = signature_ram.data.zfill(((len(signature_ram.data) + 3) // 4) * 4)
        for idx in range(0, len(data), 4):
            num = int.from_bytes(data[idx : idx + 4], "little")
            sig_file.write(hex(num)[2:].zfill(8) + "\n")
