from collections.abc import Callable
from typing import Any
from amaranth import *
from amaranth.lib.wiring import connect
from amaranth_types import ValueLike
from transactron.testing.tick_count import TicksKey

from transactron.utils import align_to_power_of_two

from transactron.testing import TestCaseWithSimulator, ProcessContext, TestbenchContext

from coreblocks.arch.isa_consts import PrivilegeLevel
from coreblocks.core import Core
from coreblocks.params import GenParams
from coreblocks.params.instr import *
from coreblocks.params.configurations import *
from coreblocks.peripherals.wishbone import WishboneMemorySlave
from coreblocks.priv.traps.interrupt_controller import ISA_RESERVED_INTERRUPTS

import random
import subprocess
import tempfile
from parameterized import parameterized_class

from transactron.utils.dependencies import DependencyContext


class CoreTestElaboratable(Elaboratable):
    def __init__(self, gen_params: GenParams, instr_mem: list[int] = [0], data_mem: list[int] = []):
        self.gen_params = gen_params
        self.instr_mem = instr_mem
        self.data_mem = data_mem

    def elaborate(self, platform):
        m = Module()

        # Align the size of the memory to the length of a cache line.
        instr_mem_depth = align_to_power_of_two(len(self.instr_mem), self.gen_params.icache_params.line_bytes_log)
        self.wb_mem_slave = WishboneMemorySlave(
            wb_params=self.gen_params.wb_params, shape=32, depth=instr_mem_depth, init=self.instr_mem
        )
        self.wb_mem_slave_data = WishboneMemorySlave(
            wb_params=self.gen_params.wb_params, shape=32, depth=len(self.data_mem), init=self.data_mem
        )

        self.core = Core(gen_params=self.gen_params)

        if self.gen_params.interrupt_custom_count == 2:
            self.interrupt_level = Signal()
            self.interrupt_edge = Signal()
            m.d.comb += self.core.interrupts.eq(
                Cat(self.interrupt_edge, self.interrupt_level) << ISA_RESERVED_INTERRUPTS
            )

        m.submodules.wb_mem_slave = self.wb_mem_slave
        m.submodules.wb_mem_slave_data = self.wb_mem_slave_data
        m.submodules.c = self.core

        connect(m, self.core.wb_instr, self.wb_mem_slave.bus)
        connect(m, self.core.wb_data, self.wb_mem_slave_data.bus)

        return m


class TestCoreBase(TestCaseWithSimulator):
    gen_params: GenParams
    m: CoreTestElaboratable

    def get_phys_reg_rrat(self, sim: TestbenchContext, reg_id):
        # TODO: abstract memories don't implement MemoryData, but standard lib.Memory used in tests
        return sim.get(self.m.core.RRAT.entries[reg_id])  # type: ignore

    def get_arch_reg_val(self, sim: TestbenchContext, reg_id):
        return sim.get(self.m.core.RF.entries.mem.data[(self.get_phys_reg_rrat(sim, reg_id))])  # type: ignore


class TestCoreAsmSourceBase(TestCoreBase):
    base_dir: str = "test/asm/"

    def prepare_source(self, filename, *, c_extension=False):
        with (
            tempfile.NamedTemporaryFile() as asm_tmp,
            tempfile.NamedTemporaryFile() as ld_tmp,
        ):
            subprocess.check_call(
                [
                    "riscv64-unknown-elf-as",
                    "-mabi=ilp32",
                    # Specified manually, because toolchains from most distributions don't support new extensioins
                    # and this test should be accessible locally.
                    f"-march=rv32im{'c' if c_extension else ''}_zicsr",
                    "-I",
                    self.base_dir,
                    "-o",
                    asm_tmp.name,
                    self.base_dir + filename,
                ]
            )
            subprocess.check_call(
                [
                    "riscv64-unknown-elf-ld",
                    "-m",
                    "elf32lriscv",
                    "-T",
                    self.base_dir + "link.ld",
                    asm_tmp.name,
                    "-o",
                    ld_tmp.name,
                ]
            )

            def load_section(section: str):
                with tempfile.NamedTemporaryFile() as bin_tmp:
                    bin = []

                    subprocess.check_call(
                        [
                            "riscv64-unknown-elf-objcopy",
                            "-O",
                            "binary",
                            "-j",
                            section,
                            ld_tmp.name,
                            bin_tmp.name,
                        ]
                    )

                    data = bin_tmp.read()
                    for word_idx in range(0, len(data), 4):
                        word = data[word_idx : word_idx + 4]
                        bin.append(int.from_bytes(word, "little"))

                    return bin

            return {"text": load_section(".text"), "data": load_section(".data")}


@parameterized_class(
    ("name", "source_file", "cycle_count", "expected_regvals", "configuration"),
    [
        ("fibonacci", "fibonacci.asm", 500, {2: 2971215073}, basic_core_config),
        ("fibonacci_mem", "fibonacci_mem.asm", 400, {3: 55}, basic_core_config),
        ("fibonacci_mem_tiny", "fibonacci_mem.asm", 250, {3: 55}, tiny_core_config),
        ("csr", "csr.asm", 200, {1: 1, 2: 4}, full_core_config),
        ("csr_mmode", "csr_mmode.asm", 1000, {1: 0, 2: 44, 3: 0, 4: 0, 5: 0, 6: 4, 15: 0}, full_core_config),
        ("exception", "exception.asm", 200, {1: 1, 2: 2}, basic_core_config),
        ("exception_mem", "exception_mem.asm", 200, {1: 1, 2: 2}, basic_core_config),
        ("exception_handler", "exception_handler.asm", 2000, {2: 987, 11: 0xAAAA, 15: 16}, full_core_config),
        ("wfi_no_int", "wfi_no_int.asm", 200, {1: 1}, full_core_config),
        ("mtval", "mtval.asm", 2000, {8: 5 * 8}, full_core_config),
    ],
)
class TestCoreBasicAsm(TestCoreAsmSourceBase):
    name: str
    source_file: str
    cycle_count: int
    expected_regvals: dict[int, int]
    configuration: CoreConfiguration

    async def run_and_check(self, sim: TestbenchContext):
        await self.tick(sim, self.cycle_count)

        for reg_id, val in self.expected_regvals.items():
            assert self.get_arch_reg_val(sim, reg_id) == val

    def test_asm_source(self):
        self.gen_params = GenParams(self.configuration)

        bin_src = self.prepare_source(self.source_file)

        if self.name == "mtval":
            bin_src["text"] = bin_src["text"][: 0x1000 // 4]  # force instruction memory size clip in `mtval` test

        self.m = CoreTestElaboratable(self.gen_params, instr_mem=bin_src["text"], data_mem=bin_src["data"])

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.run_and_check)


# test interrupts with varying triggering frequency (parametrizable amount of cycles between
# returning from an interrupt and triggering it again with 'lo' and 'hi' parameters)
@parameterized_class(
    ("source_file", "main_cycle_count", "start_regvals", "expected_regvals", "lo", "hi", "edge_only"),
    [
        (
            "interrupt.asm",
            400 * 2,
            {4: 2971215073, 8: 29},
            {2: 2971215073, 7: 29, 28: 2**7 | (3 << 11), 29: 2**3 | (3 << 11), 31: 0xDE},
            300,
            500,
            False,
        ),
        ("interrupt.asm", 700, {4: 24157817, 8: 199}, {2: 24157817, 7: 199, 31: 0xDE}, 100, 200, False),
        ("interrupt.asm", 600, {4: 89, 8: 843}, {2: 89, 7: 843, 31: 0xDE}, 30, 50, False),
        # interrupts are only inserted on branches, we always have some forward progression. 15 for trigger variantion.
        ("interrupt.asm", 80, {4: 21, 8: 9349}, {2: 21, 7: 9349, 31: 0xDE}, 0, 15, False),
        (
            "interrupt_vectored.asm",
            200,
            {4: 21, 8: 9349, 15: 24476},
            {2: 21, 7: 9349, 14: 24476, 31: 0xDE, 16: 0x201, 17: 0x111},
            0,
            15,
            False,
        ),
        ("wfi_int.asm", 80, {2: 10}, {2: 10, 3: 10}, 5, 15, True),
    ],
)
class TestCoreInterrupt(TestCoreAsmSourceBase):
    source_file: str
    main_cycle_count: int
    start_regvals: dict[int, int]
    expected_regvals: dict[int, int]
    lo: int
    hi: int
    edge_only: bool

    reg_init_mem_offset: int = 0x100

    def setup_method(self):
        self.configuration = full_core_config.replace(
            _generate_test_hardware=True, interrupt_custom_count=2, interrupt_custom_edge_trig_mask=0b01
        )
        self.gen_params = GenParams(self.configuration)
        random.seed(1500100900)

    async def clear_level_interrupt_process(self, sim: ProcessContext):
        async for *_, value in sim.tick().sample(self.m.core.csr_generic.csr_coreblocks_test.value):
            if value == 0:
                continue

            if value == 2:
                assert False, "`fail` called"

            sim.set(self.m.core.csr_generic.csr_coreblocks_test.value, 0)
            sim.set(self.m.interrupt_level, 0)

    async def run_with_interrupt_process(self, sim: TestbenchContext):
        main_cycles = 0
        int_count = 0
        handler_count = 0

        # wait for interrupt enable
        await sim.tick().until(self.m.core.interrupt_controller.mstatus_mie.value)

        async def do_interrupt():
            count = 0
            trig = random.randint(1, 3)
            mie = sim.get(self.m.core.interrupt_controller.mie.value) >> 16
            if mie != 0b11 or trig & 1 or self.edge_only:
                sim.set(self.m.interrupt_edge, 1)
                count += 1
            if (mie != 0b11 or trig & 2) and sim.get(self.m.interrupt_level) == 0 and not self.edge_only:
                sim.set(self.m.interrupt_level, 1)
                count += 1
            await sim.tick()
            sim.set(self.m.interrupt_edge, 0)
            return count

        early_interrupt = False
        while main_cycles < self.main_cycle_count or early_interrupt:
            if not early_interrupt:
                # run main code for some semi-random amount of cycles
                c = random.randrange(self.lo, self.hi)
                main_cycles += c
                await self.tick(sim, c)
                # trigger an interrupt
                int_count += await do_interrupt()

            # wait for the interrupt to get registered
            await sim.tick().until(self.m.core.interrupt_controller.mstatus_mie.value != 1)

            # trigger interrupt during execution of ISR handler (blocked-pending) with some chance
            early_interrupt = random.random() < 0.4
            if early_interrupt:
                # wait until interrupts are cleared, so it won't be missed
                await sim.tick().until(self.m.core.interrupt_controller.mip.value == 0)
                assert self.get_arch_reg_val(sim, 30) == int_count

                int_count += await do_interrupt()
            else:
                await sim.tick().until(self.m.core.interrupt_controller.mip.value == 0)
                assert self.get_arch_reg_val(sim, 30) == int_count

            handler_count += 1

            # wait until ISR returns
            await sim.tick().until(self.m.core.interrupt_controller.mstatus_mie.value != 0)

        assert self.get_arch_reg_val(sim, 30) == int_count
        assert self.get_arch_reg_val(sim, 27) == handler_count

        for reg_id, val in self.expected_regvals.items():
            assert self.get_arch_reg_val(sim, reg_id) == val

    def test_interrupted_prog(self):
        bin_src = self.prepare_source(self.source_file)
        for reg_id, val in self.start_regvals.items():
            bin_src["data"][self.reg_init_mem_offset // 4 + reg_id] = val
        self.m = CoreTestElaboratable(self.gen_params, instr_mem=bin_src["text"], data_mem=bin_src["data"])
        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.run_with_interrupt_process)
            sim.add_process(self.clear_level_interrupt_process)


@parameterized_class(
    ("source_file", "cycle_count", "expected_regvals", "always_mmode"),
    [
        ("user_mode.asm", 1100, {4: 5}, False),
        ("wfi_no_mie.asm", 250, {8: 8}, True),  # only using level enable
    ],
)
class TestCoreInterruptOnPrivMode(TestCoreAsmSourceBase):
    source_file: str
    cycle_count: int
    expected_regvals: dict[int, int]
    always_mmode: bool

    def setup_method(self):
        self.configuration = full_core_config.replace(
            _generate_test_hardware=True, interrupt_custom_count=2, interrupt_custom_edge_trig_mask=0b01
        )
        self.gen_params = GenParams(self.configuration)
        random.seed(161453)

    async def run_with_interrupt_process(self, sim: TestbenchContext):
        ticks = DependencyContext.get().get_dependency(TicksKey())

        # wait for interrupt enable
        async def wait_or_timeout(cond: ValueLike, pred: Callable[[Any], bool]):
            async for *_, value in sim.tick().sample(cond):
                if pred(value) or sim.get(ticks) >= self.cycle_count:
                    break

        await wait_or_timeout(self.m.core.interrupt_controller.mie.value, lambda value: value != 0)
        await self.random_wait(sim, 5)

        while sim.get(ticks) < self.cycle_count:
            sim.set(self.m.interrupt_level, 1)

            if self.always_mmode:  # if test happens only in m_mode, just enable fixed interrupt
                await sim.tick()
                continue

            # wait for the interrupt to get registered
            await wait_or_timeout(
                self.m.core.csr_generic.m_mode.priv_mode.value, lambda value: value == PrivilegeLevel.MACHINE
            )

            sim.set(self.m.interrupt_level, 0)

            # wait until ISR returns
            await wait_or_timeout(
                self.m.core.csr_generic.m_mode.priv_mode.value, lambda value: value != PrivilegeLevel.MACHINE
            )

            await self.random_wait(sim, 5)

        for reg_id, val in self.expected_regvals.items():
            assert self.get_arch_reg_val(sim, reg_id) == val

    def test_interrupted_prog(self):
        bin_src = self.prepare_source(self.source_file)
        self.m = CoreTestElaboratable(self.gen_params, instr_mem=bin_src["text"], data_mem=bin_src["data"])

        with self.run_simulation(self.m) as sim:
            sim.add_testbench(self.run_with_interrupt_process)
