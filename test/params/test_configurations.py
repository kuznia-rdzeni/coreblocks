from dataclasses import dataclass
from unittest import TestCase

from coreblocks.params.genparams import GenParams
from coreblocks.params.configurations import *
from coreblocks.params.isa import gen_isa_string
from coreblocks.params.fu_params import extensions_supported


class TestConfigurationsISAString(TestCase):
    @dataclass
    class ISAStrTest:
        core_config: CoreConfiguration
        partial_str: str
        full_str: str
        gp_str: str

    TEST_CASES = [
        ISAStrTest(basic_core_config, "rv32i", "rv32i", "rv32i"),
        ISAStrTest(
            full_core_config,
            "rv32imcbzicsr_xintmachinemode",
            "rv32imcbzicsr",
            "rv32imcbzicsr_xintmachinemode",
        ),
        ISAStrTest(tiny_core_config, "rv32e", "rv32", "rv32e"),
        ISAStrTest(
            interrupt_core_config,
            "rv32imbzicsr_xintmachinemode",
            "rv32imbzicsr",
            "rv32imbzicsr_xintmachinemode",
        ),
        ISAStrTest(test_core_config, "rv32", "rv32", "rv32i"),
    ]

    def test_isa_str_gp(self):
        for test in self.TEST_CASES:
            gp = GenParams(test.core_config)
            self.assertEqual(gp.isa_str, test.gp_str)

    def test_isa_str_raw(self):
        for test in self.TEST_CASES:
            partial, full = extensions_supported(
                test.core_config.func_units_config, test.core_config.embedded, test.core_config.compressed
            )

            partial = gen_isa_string(partial, 32)
            full = gen_isa_string(full, 32)

            self.assertEqual(partial, test.partial_str)
            self.assertEqual(full, test.full_str)
