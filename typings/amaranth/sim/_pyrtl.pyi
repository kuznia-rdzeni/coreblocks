"""
This type stub file was generated by pyright.
"""

from contextlib import contextmanager
from ..hdl import *
from ..hdl.xfrm import StatementVisitor, ValueVisitor
from ._base import BaseProcess

__all__ = ["PyRTLProcess"]

class PyRTLProcess(BaseProcess):
    __slots__ = ...
    def __init__(self, *, is_comb) -> None: ...
    def reset(self): ...

class _PythonEmitter:
    def __init__(self) -> None: ...
    def append(self, code): ...
    @contextmanager
    def indent(self): ...
    def flush(self, indent=...): ...
    def gen_var(self, prefix): ...
    def def_var(self, prefix, value): ...

class _Compiler:
    def __init__(self, state, emitter) -> None: ...

class _ValueCompiler(ValueVisitor, _Compiler):
    helpers = ...
    def on_value(self, value): ...
    def on_ClockSignal(self, value): ...
    def on_ResetSignal(self, value): ...
    def on_AnyConst(self, value): ...
    def on_AnySeq(self, value): ...
    def on_Sample(self, value): ...
    def on_Initial(self, value): ...

class _RHSValueCompiler(_ValueCompiler):
    def __init__(self, state, emitter, *, mode, inputs=...) -> None: ...
    def on_Const(self, value): ...
    def on_Signal(self, value): ...
    def on_Operator(self, value): ...
    def on_Slice(self, value): ...
    def on_Part(self, value): ...
    def on_Cat(self, value): ...
    def on_Repl(self, value): ...
    def on_ArrayProxy(self, value): ...
    @classmethod
    def compile(cls, state, value, *, mode): ...

class _LHSValueCompiler(_ValueCompiler):
    def __init__(self, state, emitter, *, rhs, outputs=...) -> None: ...
    def on_Const(self, value): ...
    def on_Signal(self, value): ...
    def on_Operator(self, value): ...
    def on_Slice(self, value): ...
    def on_Part(self, value): ...
    def on_Cat(self, value): ...
    def on_Repl(self, value): ...
    def on_ArrayProxy(self, value): ...

class _StatementCompiler(StatementVisitor, _Compiler):
    def __init__(self, state, emitter, *, inputs=..., outputs=...) -> None: ...
    def on_statements(self, stmts): ...
    def on_Assign(self, stmt): ...
    def on_Switch(self, stmt): ...
    def on_Assert(self, stmt): ...
    def on_Assume(self, stmt): ...
    def on_Cover(self, stmt): ...
    @classmethod
    def compile(cls, state, stmt): ...

class _FragmentCompiler:
    def __init__(self, state) -> None: ...
    def __call__(self, fragment): ...
