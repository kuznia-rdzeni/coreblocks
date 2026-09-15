import cocotb_tools
import cocotb_tools.config
from cocotb_tools.runner import Verilator, _Command
from typing import Optional
from multiprocessing import cpu_count


class VerilatorManualPublic(Verilator):
    def __init__(self, skip_build: bool = False, *args, **kwargs):
        self.skip_build = skip_build
        super().__init__(*args, **kwargs)

    def _waves_file(self) -> Optional[str]:
        return "dump.fst"  # originally dump.vcd

    def _build_command(self) -> list[_Command]:
        self._simulator_in_path_build_only()

        # for checking
        super()._build_command()

        if self.skip_build:
            return []

        sources = self._sources + self._verilog_sources

        # TODO: set "--debug" if self.verbose
        # TODO: support "--always"

        verilator_cpp = str(cocotb_tools.config.share_dir / "lib" / "verilator" / "verilator.cpp")

        cmds = []
        cmds.append(
            [
                "perl",
                self.executable,
                "-cc",
                "--exe",
                "-Mdir",
                str(self.build_dir),
                "--top-module",
                self.hdl_toplevel,
                "--vpi",
                "--public-flat-rw",
                "--prefix",
                "Vtop",
                "-o",
                self.hdl_toplevel,
                "-LDFLAGS",
                f"-Wl,-rpath,{cocotb_tools.config.libs_dir} -L{cocotb_tools.config.libs_dir} -lcocotbvpi_verilator",
            ]
            + (["--trace-fst", "--trace-structs"] if self.waves else [])  # originally "--trace"
            + [arg.value for arg in self._build_args]
            + (["--timescale", "{}/{}".format(*self.timescale)] if self.timescale is not None else [])
            + self._get_define_options(self.defines)
            + self._get_include_options(self.includes)
            + self._get_parameter_options(self.parameters)
            + [verilator_cpp]
            + [str(source.value) for source in sources]
        )

        cmds.append(
            [
                "make",
                "-j",
                f"{cpu_count()}",
                "-C",
                str(self.build_dir),
                "-f",
                "Vtop.mk",
                f"VM_TRACE={int(self.waves)}",
            ]
        )

        return cmds
