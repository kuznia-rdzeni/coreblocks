from amaranth import *
from amaranth.hdl.dsl import FSM, _ModuleBuilderDomain
from typing import Optional, NoReturn, TYPE_CHECKING, Callable
from contextlib import contextmanager
from .typing import ModuleLike, ValueLike, SwitchKey, RecordDict
from .._utils import method_def_helper
from coreblocks.utils import assign, AssignType

__all__ = [
    "TModule",
    "TransactionContext",
    "def_method",
]

if TYPE_CHECKING:
    from .method import Method
    from .manager import TransactionManager


class _AvoidingModuleBuilderDomains:
    _m: "TModule"

    def __init__(self, m: "TModule"):
        object.__setattr__(self, "_m", m)

    def __getattr__(self, name: str) -> _ModuleBuilderDomain:
        if name == "av_comb":
            return self._m.avoiding_module.d["comb"]
        elif name == "top_comb":
            return self._m.top_module.d["comb"]
        else:
            return self._m.main_module.d[name]

    def __getitem__(self, name: str) -> _ModuleBuilderDomain:
        return self.__getattr__(name)

    def __setattr__(self, name: str, value):
        if not isinstance(value, _ModuleBuilderDomain):
            raise AttributeError(f"Cannot assign 'd.{name}' attribute; did you mean 'd.{name} +='?")

    def __setitem__(self, name: str, value):
        return self.__setattr__(name, value)


class TModule(ModuleLike, Elaboratable):
    """Extended Amaranth module for use with transactions.

    It includes three different combinational domains:

    * `comb` domain, works like the `comb` domain in plain Amaranth modules.
      Statements in `comb` are guarded by every condition, including
      `AvoidedIf`. This means they are guarded by transaction and method
      bodies: they don't execute if the given transaction/method is not run.
    * `av_comb` is guarded by all conditions except `AvoidedIf`. This means
      they are not guarded by transaction and method bodies. This allows to
      reduce the amount of useless multplexers due to transaction use, while
      still allowing the use of conditions in transaction/method bodies.
    * `top_comb` is unguarded: statements added to this domain always
      execute. It can be used to reduce combinational path length due to
      multplexers while keeping related combinational and synchronous
      statements together.
    """

    def __init__(self):
        self.main_module = Module()
        self.avoiding_module = Module()
        self.top_module = Module()
        self.d = _AvoidingModuleBuilderDomains(self)
        self.submodules = self.main_module.submodules
        self.domains = self.main_module.domains
        self.fsm: Optional[FSM] = None

    @contextmanager
    def AvoidedIf(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            yield

    @contextmanager
    def If(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.avoiding_module.If(cond):
                yield

    @contextmanager
    def Elif(self, cond):  # noqa: N802
        with self.main_module.Elif(cond):
            with self.avoiding_module.Elif(cond):
                yield

    @contextmanager
    def Else(self):  # noqa: N802
        with self.main_module.Else():
            with self.avoiding_module.Else():
                yield

    @contextmanager
    def Switch(self, test: ValueLike):  # noqa: N802
        with self.main_module.Switch(test):
            with self.avoiding_module.Switch(test):
                yield

    @contextmanager
    def Case(self, *patterns: SwitchKey):  # noqa: N802
        with self.main_module.Case(*patterns):
            with self.avoiding_module.Case(*patterns):
                yield

    @contextmanager
    def Default(self):  # noqa: N802
        with self.main_module.Default():
            with self.avoiding_module.Default():
                yield

    @contextmanager
    def FSM(self, reset: Optional[str] = None, domain: str = "sync", name: str = "fsm"):  # noqa: N802
        old_fsm = self.fsm
        with self.main_module.FSM(reset, domain, name) as fsm:
            self.fsm = fsm
            yield fsm
        self.fsm = old_fsm

    @contextmanager
    def State(self, name: str):  # noqa: N802
        assert self.fsm is not None
        with self.main_module.State(name):
            with self.avoiding_module.If(self.fsm.ongoing(name)):
                yield

    @property
    def next(self) -> NoReturn:
        raise NotImplementedError

    @next.setter
    def next(self, name: str):
        self.main_module.next = name

    @property
    def _MustUse__silence(self):  # noqa: N802
        return self.main_module._MustUse__silence

    @_MustUse__silence.setter
    def _MustUse__silence(self, value):  # noqa: N802
        self.main_module._MustUse__silence = value  # type: ignore
        self.avoiding_module._MustUse__silence = value  # type: ignore
        self.top_module._MustUse__silence = value  # type: ignore

    def elaborate(self, platform):
        self.main_module.submodules._avoiding_module = self.avoiding_module
        self.main_module.submodules._top_module = self.top_module
        return self.main_module


class TransactionContext:
    stack: list["TransactionManager"] = []

    def __init__(self, manager: "TransactionManager"):
        self.manager = manager

    def __enter__(self):
        self.stack.append(self.manager)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        top = self.stack.pop()
        assert self.manager is top

    @classmethod
    def get(cls) -> "TransactionManager":
        if not cls.stack:
            raise RuntimeError("TransactionContext stack is empty")
        return cls.stack[-1]


def def_method(m: TModule, method: "Method", ready: ValueLike = C(1)):
    """Define a method.

    This decorator allows to define transactional methods in an
    elegant way using Python's `def` syntax. Internally, `def_method`
    uses `Method.body`.

    The decorated function should take keyword arguments corresponding to the
    fields of the method's input layout. The `**kwargs` syntax is supported.
    Alternatively, it can take one argument named `arg`, which will be a
    record with input signals.

    The returned value can be either a record with the method's output layout
    or a dictionary of outputs.

    Parameters
    ----------
    m: TModule
        Module in which operations on signals should be executed.
    method: Method
        The method whose body is going to be defined.
    ready: Signal
        Signal to indicate if the method is ready to be run. By
        default it is `Const(1)`, so the method is always ready.
        Assigned combinationally to the `ready` attribute.

    Examples
    --------
    .. highlight:: python
    .. code-block:: python

        m = Module()
        my_sum_method = Method(i=[("arg1",8),("arg2",8)], o=[("res",8)])
        @def_method(m, my_sum_method)
        def _(arg1, arg2):
            return arg1 + arg2

    Alternative syntax (keyword args in dictionary):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(**args):
            return args["arg1"] + args["arg2"]

    Alternative syntax (arg record):

    .. highlight:: python
    .. code-block:: python

        @def_method(m, my_sum_method)
        def _(arg):
            return {"res": arg.arg1 + arg.arg2}
    """

    def decorator(func: Callable[..., Optional[RecordDict]]):
        out = Record.like(method.data_out)
        ret_out = None

        with method.body(m, ready=ready, out=out) as arg:
            ret_out = method_def_helper(method, func, arg, **arg.fields)

        if ret_out is not None:
            m.d.top_comb += assign(out, ret_out, fields=AssignType.ALL)

    return decorator
