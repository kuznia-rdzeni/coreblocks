"""
This type stub file was generated by pyright.
"""

from ..hdl import *
from ..build import *

class GowinPlatform(TemplatedPlatform):
    """
    .. rubric:: Apicula toolchain

    Required tools:
        * ``yosys``
        * ``nextpnr-gowin``
        * ``gowin_pack``

    The environment is populated by running the script specified in the environment variable
    ``AMARANTH_ENV_APICULA``, if present.

    Build products:
        * ``{{name}}.fs``: binary bitstream.

    .. rubric:: Gowin toolchain

    Required tools:
        * ``gw_sh``

    The environment is populated by running the script specified in the environment variable
    ``AMARANTH_ENV_GOWIN``, if present.

    Build products:
        * ``{{name}}.fs``: binary bitstream.
    """
    toolchain = ...
    part = ...
    family = ...
    def parse_part(self): # -> None:
        ...
    
    _dev_osc_mapping = ...
    _common_file_templates = ...
    _apicula_required_tools = ...
    _apicula_file_templates = ...
    _apicula_command_templates = ...
    _gowin_required_tools = ...
    _gowin_file_templates = ...
    _gowin_command_templates = ...
    def __init__(self, *, toolchain=...) -> None:
        ...
    
    @property
    def required_tools(self): # -> list[str]:
        ...
    
    @property
    def file_templates(self): # -> dict[str, str]:
        ...
    
    @property
    def command_templates(self): # -> list[str]:
        ...
    
    def add_clock_constraint(self, clock, frequency): # -> None:
        ...
    
    @property
    def default_clk_constraint(self): # -> Clock:
        ...
    
    def create_missing_domain(self, name): # -> Module | None:
        ...
    
    def get_input(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_output(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_tristate(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_input_output(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_diff_input(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_diff_output(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_diff_tristate(self, pin, port, attrs, invert): # -> Module:
        ...
    
    def get_diff_input_output(self, pin, port, attrs, invert): # -> Module:
        ...
    


