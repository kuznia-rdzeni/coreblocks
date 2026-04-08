from dataclasses import dataclass
from unittest import TestCase

from coreblocks.arch.isa import gen_isa_string
from coreblocks.params.configurations import *
from coreblocks.params.fu_params import extensions_supported
from coreblocks.params.genparams import GenParams


class TestConfigurationsISAString(TestCase):
    @dataclass
    class ISAStrTest:
        core_config: CoreConfiguration
        partial_str: str
        full_str: str
        gp_str: str

    TEST_CASES = [
        ISAStrTest(
            basic_core_config,
            "rv32imzicsr_zifencei_xintmachinemode",
            "rv32imzicsr_zifencei_xintmachinemode",
            "rv32imzicsr_zifencei_xintmachinemode",
        ),
        ISAStrTest(
            small_linux_config,
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
        ),
        ISAStrTest(
            full_core_config,
            "rv32imacbzicond_zicsr_zifencei_zbc_zbkx_xintmachinemode_xintsupervisor",
            "rv32imacbzicond_zicsr_zifencei_zbc_zbkx_xintmachinemode_xintsupervisor",
            "rv32imacbzicond_zicsr_zifencei_zbc_zbkx_xintmachinemode_xintsupervisor",
        ),
        ISAStrTest(tiny_core_config, "rv32e", "rv32e", "rv32e"),
        ISAStrTest(test_core_config, "rv32", "rv32", "rv32i"),
    ]

    def test_isa_str_gp(self):
        for test in self.TEST_CASES:
            gp = GenParams(test.core_config)
            assert gp.isa_str == test.gp_str

    def test_isa_str_raw(self):
        for test in self.TEST_CASES:
            partial, full = extensions_supported(
                test.core_config.func_units_config,
                test.core_config.embedded,
                test.core_config.compressed,
            )

            partial = gen_isa_string(partial, 32)
            full = gen_isa_string(full, 32)

            assert partial == test.partial_str
            assert full == test.full_str
