from enum import Enum, auto
from dataclasses import dataclass, replace
from amaranth import *
from typing import Optional, Self, NoReturn
from contextlib import contextmanager
from amaranth.hdl._dsl import FSM
from transactron.utils import *

__all__ = ["TModule"]


class _AvoidingModuleBuilderDomain:
    """
    A wrapper over Amaranth domain to abstract away internal Amaranth implementation.
    It is needed to allow for correctness check in `__setattr__` which uses `isinstance`.
    """

    def __init__(self, amaranth_module_domain):
        self._domain = amaranth_module_domain

    def __iadd__(self, assigns: StatementLike) -> Self:
        self._domain.__iadd__(assigns)
        return self


class _AvoidingModuleBuilderDomains:
    _m: "TModule"

    def __init__(self, m: "TModule"):
        object.__setattr__(self, "_m", m)

    def __getattr__(self, name: str) -> _AvoidingModuleBuilderDomain:
        if name == "av_comb":
            return _AvoidingModuleBuilderDomain(self._m.avoiding_module.d["comb"])
        elif name == "top_comb":
            return _AvoidingModuleBuilderDomain(self._m.top_module.d["comb"])
        else:
            return _AvoidingModuleBuilderDomain(self._m.main_module.d[name])

    def __getitem__(self, name: str) -> _AvoidingModuleBuilderDomain:
        return self.__getattr__(name)

    def __setattr__(self, name: str, value):
        if not isinstance(value, _AvoidingModuleBuilderDomain):
            raise AttributeError(f"Cannot assign 'd.{name}' attribute; did you mean 'd.{name} +='?")

    def __setitem__(self, name: str, value):
        return self.__setattr__(name, value)


class EnterType(Enum):
    """Characterizes stack behavior of Amaranth's context managers for control structures."""

    #: Used for `m.If`, `m.Switch` and `m.FSM`.
    PUSH = auto()
    #: Used for `m.Elif` and `m.Else`.
    ADD = auto()
    #: Used for `m.Case`, `m.Default` and `m.State`.
    ENTRY = auto()


@dataclass(frozen=True)
class PathEdge:
    """Describes an edge in Amaranth's control tree.

    Attributes
    ----------
    alt : int
        Which alternative (e.g. case of `m.If` or m.Switch`) is described.
    par : int
        Which parallel control structure (e.g. `m.If` at the same level) is described.
    """

    alt: int = 0
    par: int = 0


@dataclass
class CtrlPath:
    """Describes a path in Amaranth's control tree.

    Attributes
    ----------
    module : int
        Unique number of the module the path refers to.
    path : list[PathEdge]
        Path in the control tree, starting from the root.
    """

    module: int
    path: list[PathEdge]

    def exclusive_with(self, other: "CtrlPath"):
        """Decides if this path is mutually exclusive with some other path.

        Paths are mutually exclusive if they refer to the same module and
        diverge on different alternatives of the same control structure.

        Arguments
        ---------
        other : CtrlPath
            The other path this path is compared to.
        """
        common_prefix = []
        for a, b in zip(self.path, other.path):
            if a == b:
                common_prefix.append(a)
            elif a.par != b.par:
                return False
            else:
                break

        return (
            self.module == other.module
            and len(common_prefix) != len(self.path)
            and len(common_prefix) != len(other.path)
        )


class CtrlPathBuilder:
    """Constructs control paths.

    Used internally by `TModule`."""

    def __init__(self, module: int):
        """
        Parameters
        ----------
        module: int
            Unique module identifier.
        """
        self.module = module
        self.ctrl_path: list[PathEdge] = []
        self.previous: Optional[PathEdge] = None

    @contextmanager
    def enter(self, enter_type=EnterType.PUSH):
        et = EnterType

        match enter_type:
            case et.ADD:
                assert self.previous is not None
                self.ctrl_path.append(replace(self.previous, alt=self.previous.alt + 1))
            case et.ENTRY:
                self.ctrl_path[-1] = replace(self.ctrl_path[-1], alt=self.ctrl_path[-1].alt + 1)
            case et.PUSH:
                if self.previous is not None:
                    self.ctrl_path.append(PathEdge(par=self.previous.par + 1))
                else:
                    self.ctrl_path.append(PathEdge())
        self.previous = None
        try:
            yield
        finally:
            if enter_type in [et.PUSH, et.ADD]:
                self.previous = self.ctrl_path.pop()

    def build_ctrl_path(self):
        """Returns the current control path."""
        return CtrlPath(self.module, self.ctrl_path[:])


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

    __next_uid = 0

    def __init__(self):
        self.main_module = Module()
        self.avoiding_module = Module()
        self.top_module = Module()
        self.d = _AvoidingModuleBuilderDomains(self)
        self.submodules = self.main_module.submodules
        self.domains = self.main_module.domains
        self.fsm: Optional[FSM] = None
        self.uid = TModule.__next_uid
        self.path_builder = CtrlPathBuilder(self.uid)
        TModule.__next_uid += 1

    @contextmanager
    def AvoidedIf(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.path_builder.enter(EnterType.PUSH):
                yield

    @contextmanager
    def If(self, cond: ValueLike):  # noqa: N802
        with self.main_module.If(cond):
            with self.avoiding_module.If(cond):
                with self.path_builder.enter(EnterType.PUSH):
                    yield

    @contextmanager
    def Elif(self, cond):  # noqa: N802
        with self.main_module.Elif(cond):
            with self.avoiding_module.Elif(cond):
                with self.path_builder.enter(EnterType.ADD):
                    yield

    @contextmanager
    def Else(self):  # noqa: N802
        with self.main_module.Else():
            with self.avoiding_module.Else():
                with self.path_builder.enter(EnterType.ADD):
                    yield

    @contextmanager
    def Switch(self, test: ValueLike):  # noqa: N802
        with self.main_module.Switch(test):
            with self.avoiding_module.Switch(test):
                with self.path_builder.enter(EnterType.PUSH):
                    yield

    @contextmanager
    def Case(self, *patterns: SwitchKey):  # noqa: N802
        with self.main_module.Case(*patterns):
            with self.avoiding_module.Case(*patterns):
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @contextmanager
    def Default(self):  # noqa: N802
        with self.main_module.Default():
            with self.avoiding_module.Default():
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @contextmanager
    def FSM(self, init: Optional[str] = None, domain: str = "sync", name: str = "fsm"):  # noqa: N802
        old_fsm = self.fsm
        with self.main_module.FSM(init, domain, name) as fsm:
            self.fsm = fsm
            with self.path_builder.enter(EnterType.PUSH):
                yield fsm
        self.fsm = old_fsm

    @contextmanager
    def State(self, name: str):  # noqa: N802
        assert self.fsm is not None
        with self.main_module.State(name):
            with self.avoiding_module.If(self.fsm.ongoing(name)):
                with self.path_builder.enter(EnterType.ENTRY):
                    yield

    @property
    def next(self) -> NoReturn:
        raise NotImplementedError

    @next.setter
    def next(self, name: str):
        self.main_module.next = name

    @property
    def ctrl_path(self):
        return self.path_builder.build_ctrl_path()

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
