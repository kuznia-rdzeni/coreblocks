"""
This type stub file was generated by pyright.
"""

import os
import shutil

__all__ = ["ToolNotFound", "tool_env_var", "has_tool", "require_tool"]

class ToolNotFound(Exception): ...

def tool_env_var(name): ...
def has_tool(name): ...
def require_tool(name): ...
