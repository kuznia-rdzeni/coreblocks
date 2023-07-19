"""
This type stub file was generated by pyright.
"""

from abc import ABCMeta, abstractmethod
from .._toolchain import *
from ..hdl import *
from .res import *
from .run import *

__all__ = ["Platform", "TemplatedPlatform"]
class Platform(ResourceManager, metaclass=ABCMeta):
    resources = ...
    connectors = ...
    default_clk = ...
    default_rst = ...
    required_tools = ...
    def __init__(self) -> None:
        ...
    
    @property
    def default_clk_constraint(self):
        ...
    
    @property
    def default_clk_frequency(self):
        ...
    
    def add_file(self, filename, content): # -> None:
        ...
    
    def iter_files(self, *suffixes): # -> Generator[Unknown, Any, None]:
        ...
    
    def build(self, elaboratable, name=..., build_dir=..., do_build=..., program_opts=..., do_program=..., **kwargs): # -> None:
        ...
    
    def has_required_tools(self): # -> bool:
        ...
    
    def create_missing_domain(self, name): # -> Module | None:
        ...
    
    def prepare(self, elaboratable, name=..., **kwargs):
        ...
    
    @abstractmethod
    def toolchain_prepare(self, fragment, name, **kwargs):
        """
        Convert the ``fragment`` and constraints recorded in this :class:`Platform` into
        a :class:`BuildPlan`.
        """
        ...
    
    def toolchain_program(self, products, name, **kwargs):
        """
        Extract bitstream for fragment ``name`` from ``products`` and download it to a target.
        """
        ...
    
    def get_input(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_output(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_tristate(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_input_output(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_diff_input(self, pin, port, attrs, invert): # -> None:
        ...
    
    def get_diff_output(self, pin, port, attrs, invert): # -> None:
        ...
    
    def get_diff_tristate(self, pin, port, attrs, invert): # -> None:
        ...
    
    def get_diff_input_output(self, pin, port, attrs, invert): # -> None:
        ...
    


class TemplatedPlatform(Platform):
    toolchain = ...
    file_templates = ...
    command_templates = ...
    build_script_templates = ...
    def iter_clock_constraints(self): # -> Generator[tuple[Unknown, Unknown | None, Unknown], Any, None]:
        ...
    
    def toolchain_prepare(self, fragment, name, **kwargs): # -> BuildPlan:
        ...
    


