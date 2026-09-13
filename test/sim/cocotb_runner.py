import cocotb_tools
import cocotb_tools.config
from cocotb_tools.runner import Verilator, _get_max_parallel_build_jobs, _Command, Verilog, VerilatorControlFile
from typing import Optional

class VerilatorManualPublic(Verilator):
    def __init__(self, skip_build: bool = False, *args, **kwargs):
        self.skip_build = skip_build
        super().__init__(*args, **kwargs)

    def _waves_file(self) -> Optional[str]:
        return "dump.fst"  # originally dump.vcd

    def _build_command(self) -> list[_Command]:
        self._simulator_in_path_build_only()

        if self.skip_build:
            return []

        sources = self._sources + self._verilog_sources

        for source in sources:
            if source.tag not in (Verilog, VerilatorControlFile):
                raise ValueError(
                    f"{type(self).__qualname__} only supports Verilog and Verilator Control Files. {str(source.value)!r} cannot be compiled."
                )

        for arg in self._build_args:
            if arg.tag not in (Verilog, None):
                raise ValueError(
                    f"{type(self).__qualname__} only supports Verilog. build_args {arg.value!r} will not be applied."
                )

        if self.hdl_toplevel is None:
            raise ValueError(
                f"{type(self).__qualname__} requires the hdl_toplevel parameter to be specified."
            )

        # TODO: set "--debug" if self.verbose
        # TODO: support "--always"

        verilator_cpp = str(
            cocotb_tools.config.share_dir / "lib" / "verilator" / "verilator.cpp"
        )

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
            + (["--trace-fst", "--trace-structs"] if self.waves else [])
            + [arg.value for arg in self._build_args]
            + (
                ["--timescale", "{}/{}".format(*self.timescale)]
                if self.timescale is not None
                else []
            )
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
                f"{_get_max_parallel_build_jobs()}",
                "-C",
                str(self.build_dir),
                "-f",
                "Vtop.mk",
                f"VM_TRACE={int(self.waves)}",
            ]
        )

        return cmds
