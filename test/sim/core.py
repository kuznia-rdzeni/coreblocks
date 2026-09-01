"""The core which the regression suites run on."""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from coreblocks.core import Core
from coreblocks.gen_verilog import gen_verilog
from coreblocks.params import GenParams, configurations
from coreblocks.params.core_configuration import CoreConfiguration
from coreblocks.socks.socks import Socks

START_PC = 0x80000000


@contextmanager
def _environment(**variables: Optional[str]) -> Iterator[None]:
    """Sets environment variables for the duration of the block."""
    previous = {name: os.environ.get(name) for name in variables}
    try:
        os.environ.update({name: value for name, value in variables.items() if value is not None})
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@dataclass(frozen=True)
class SimulatedCore:
    """A core configuration, and the two ways of turning it into something runnable."""

    config: CoreConfiguration
    with_socks: bool = True

    def gen_params(self) -> GenParams:
        return GenParams(self.config)

    def elaborate(self, gen_params: GenParams) -> Core | Socks:
        core = Core(gen_params=gen_params)
        if self.with_socks:
            return Socks(core, core_gen_params=gen_params)
        return core

    def generate_verilog(self, output_path: Path):
        # The same variable makes a simulation capture event logs, so it must not
        # leak into the rest of the process.
        with _environment(__TRANSACTRON_EVLOG="1"):
            gen_verilog(self.config, str(output_path), wrap_socks=self.with_socks)


REGRESSION_CORE = SimulatedCore(config=configurations.full.replace(start_pc=START_PC, with_rvvi=True))
