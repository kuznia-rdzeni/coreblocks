import sys
from contextlib import contextmanager
from typing import Optional, Any, Concatenate, TypeGuard, TypeVar
from collections.abc import Callable, Mapping
from ._typing import ROGraph, GraphCC, SrcLoc, MethodLayout, MethodStruct, ShapeLike, LayoutList, LayoutListField
from inspect import Parameter, signature
from itertools import count
from amaranth import *
from amaranth import tracer
from amaranth.lib.data import StructLayout


__all__ = [
    "silence_mustuse",
    "get_caller_class_name",
    "def_helper",
    "method_def_helper",
    "mock_def_helper",
    "get_src_loc",
    "from_method_layout",
    "make_layout",
]

T = TypeVar("T")
U = TypeVar("U")


def _graph_ccs(gr: ROGraph[T]) -> list[GraphCC[T]]:
    """_graph_ccs

    Find connected components in a graph.

    Parameters
    ----------
    gr : Mapping[T, Iterable[T]]
        Graph in which we should find connected components. Encoded using
        adjacency lists.

    Returns
    -------
    ccs : List[Set[T]]
        Connected components of the graph `gr`.
    """
    ccs = []
    cc = set()
    visited = set()

    for v in gr.keys():
        q = [v]
        while q:
            w = q.pop()
            if w in visited:
                continue
            visited.add(w)
            cc.add(w)
            q.extend(gr[w])
        if cc:
            ccs.append(cc)
            cc = set()

    return ccs


def has_first_param(func: Callable[..., T], name: str, tp: type[U]) -> TypeGuard[Callable[Concatenate[U, ...], T]]:
    parameters = signature(func).parameters
    return (
        len(parameters) >= 1
        and next(iter(parameters)) == name
        and parameters[name].kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.POSITIONAL_ONLY}
        and parameters[name].annotation in {Parameter.empty, tp}
    )


def def_helper(description, func: Callable[..., T], tp: type[U], arg: U, /, **kwargs) -> T:
    try:
        parameters = signature(func).parameters
    except ValueError:
        raise TypeError(f"Invalid python method signature for {func} (missing `self` for class-level mock?)")

    kw_parameters = set(
        n for n, p in parameters.items() if p.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY}
    )
    if len(parameters) == 1 and has_first_param(func, "arg", tp):
        return func(arg)
    elif kw_parameters <= kwargs.keys():
        return func(**kwargs)
    else:
        raise TypeError(f"Invalid {description}: {func}")


def mock_def_helper(tb, func: Callable[..., T], arg: Mapping[str, Any]) -> T:
    return def_helper(f"mock definition for {tb}", func, Mapping[str, Any], arg, **arg)


def method_def_helper(method, func: Callable[..., T], arg: MethodStruct) -> T:
    kwargs = {k: arg[k] for k in arg.shape().members}
    return def_helper(f"method definition for {method}", func, MethodStruct, arg, **kwargs)


def get_caller_class_name(default: Optional[str] = None) -> tuple[Optional[Elaboratable], str]:
    try:
        for d in count(2):
            caller_frame = sys._getframe(d)
            if "self" in caller_frame.f_locals:
                owner = caller_frame.f_locals["self"]
                if isinstance(owner, Elaboratable):
                    return owner, owner.__class__.__name__
    except ValueError:
        pass

    if default is not None:
        return None, default
    else:
        raise RuntimeError("Not called from a method")


@contextmanager
def silence_mustuse(elaboratable: Elaboratable):
    try:
        yield
    except Exception:
        elaboratable._MustUse__silence = True  # type: ignore
        raise


def get_src_loc(src_loc: int | SrcLoc) -> SrcLoc:
    return tracer.get_src_loc(1 + src_loc) if isinstance(src_loc, int) else src_loc


def from_layout_field(shape: ShapeLike | LayoutList) -> ShapeLike:
    if isinstance(shape, list):
        return from_method_layout(shape)
    else:
        return shape


def make_layout(*fields: LayoutListField) -> StructLayout:
    return from_method_layout(fields)


def from_method_layout(layout: MethodLayout) -> StructLayout:
    if isinstance(layout, StructLayout):
        return layout
    else:
        return StructLayout({k: from_layout_field(v) for k, v in layout})
