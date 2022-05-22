"""
This type stub file was generated by pyright.
"""

__all__ = ["YosysError", "YosysBinary", "find_yosys"]

class YosysError(Exception): ...
class YosysWarning(Warning): ...

class YosysBinary:
    @classmethod
    def available(cls):
        """Check for Yosys availability."""
        ...
    @classmethod
    def version(cls):
        """Get Yosys version.

        Retu"""
        ...
    @classmethod
    def data_dir(cls):
        """Get Yosys data directory."""
        ...
    @classmethod
    def run(cls, args, stdin=...):
        """Run Yosys process.

        Para"""
        ...

class _BuiltinYosys(YosysBinary):
    YOSYS_PACKAGE = ...
    @classmethod
    def available(cls): ...
    @classmethod
    def version(cls): ...
    @classmethod
    def data_dir(cls): ...
    @classmethod
    def run(cls, args, stdin=..., *, ignore_warnings=..., src_loc_at=...): ...

class _SystemYosys(YosysBinary):
    YOSYS_BINARY = ...
    @classmethod
    def available(cls): ...
    @classmethod
    def version(cls): ...
    @classmethod
    def data_dir(cls): ...
    @classmethod
    def run(cls, args, stdin=..., *, ignore_warnings=..., src_loc_at=...): ...

def find_yosys(requirement):
    """Find an available Yosys executab"""
    ...
