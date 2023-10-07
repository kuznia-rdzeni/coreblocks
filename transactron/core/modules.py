from amaranth import *
from amaranth.hdl.dsl import FSM, _ModuleBuilderDomain
from typing import Optional, NoReturn
from contextlib import contextmanager
from .typing import ModuleLike, ValueLike, SwitchKey

__all__ = [
    "TModule",
]


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
