from dataclasses import dataclass
from unittest import TestCase

from coreblocks.arch.isa import gen_isa_string
from coreblocks.params.core_configuration import CoreConfiguration
from coreblocks.params import configurations
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
            configurations.basic,
            "rv32imzicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imzicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imzicsr_zifencei_xintmachinemode_xintsupervisor",
        ),
        ISAStrTest(
            configurations.small_linux,
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
            "rv32imazicsr_zifencei_xintmachinemode_xintsupervisor",
        ),
        ISAStrTest(
            configurations.full,
            "rv32imacbzicond_zicsr_zifencei_zcb_zbc_zbkx_xintmachinemode_xintsupervisor",
            "rv32imacbzicond_zicsr_zifencei_zcb_zbc_zbkx_xintmachinemode_xintsupervisor",
            "rv32imacbzicond_zicsr_zifencei_zcb_zbc_zbkx_xintmachinemode_xintsupervisor",
        ),
        ISAStrTest(configurations.tiny, "rv32e", "rv32e", "rv32e"),
        ISAStrTest(configurations.test, "rv32", "rv32", "rv32i"),
    ]

    def test_isa_str_gp(self):
        for test in self.TEST_CASES:
            gp = GenParams(test.core_config)
            assert gp.isa_str == test.gp_str

    def test_isa_str_raw(self):
        for test in self.TEST_CASES:
            xlen = int(test.partial_str[2:4])
            partial, full = extensions_supported(
                test.core_config.func_units_config,
                test.core_config.embedded,
                test.core_config.compressed,
                test.core_config.zcb,
            )

            partial = gen_isa_string(partial, xlen)
            full = gen_isa_string(full, xlen)

            assert partial == test.partial_str
            assert full == test.full_str
