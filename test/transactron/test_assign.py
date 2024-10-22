import pytest
from typing import Callable
from amaranth import *
from amaranth.lib import data
from amaranth.lib.enum import Enum
from amaranth.hdl._ast import ArrayProxy, SwitchValue, Slice

from transactron.utils._typing import MethodLayout
from transactron.utils import AssignType, assign
from transactron.utils.assign import AssignArg, AssignFields

from unittest import TestCase
from parameterized import parameterized_class, parameterized


class ExampleEnum(Enum, shape=1):
    ZERO = 0
    ONE = 1


def with_reversed(pairs: list[tuple[str, str]]):
    return pairs + [(b, a) for (a, b) in pairs]


layout_a = [("a", 1)]
layout_ab = [("a", 1), ("b", 2)]
layout_ac = [("a", 1), ("c", 3)]
layout_a_alt = [("a", 2)]
layout_a_enum = [("a", ExampleEnum)]

# Defines functions build, wrap, extr used in TestAssign
params_funs = {
    "normal": (lambda mk, lay: mk(lay), lambda x: x, lambda r: r),
    "rec": (lambda mk, lay: mk([("x", lay)]), lambda x: {"x": x}, lambda r: r.x),
    "dict": (lambda mk, lay: {"x": mk(lay)}, lambda x: {"x": x}, lambda r: r["x"]),
    "list": (lambda mk, lay: [mk(lay)], lambda x: {0: x}, lambda r: r[0]),
    "union": (
        lambda mk, lay: Signal(data.UnionLayout({"x": reclayout2datalayout(lay)})),
        lambda x: {"x": x},
        lambda r: r.x,
    ),
    "array": (lambda mk, lay: Signal(data.ArrayLayout(reclayout2datalayout(lay), 1)), lambda x: {0: x}, lambda r: r[0]),
}


params_pairs = [(k, k) for k in params_funs if k != "union"] + with_reversed(
    [("rec", "dict"), ("list", "array"), ("union", "dict")]
)


def mkproxy(layout):
    arr = Array([Signal(reclayout2datalayout(layout)) for _ in range(4)])
    sig = Signal(2)
    return arr[sig]


def reclayout2datalayout(layout):
    if not isinstance(layout, list):
        return layout
    return data.StructLayout({k: reclayout2datalayout(lay) for k, lay in layout})


def mkstruct(layout):
    return Signal(reclayout2datalayout(layout))


params_mk = [
    ("proxy", mkproxy),
    ("struct", mkstruct),
]


@parameterized_class(
    ["name", "buildl", "wrapl", "extrl", "buildr", "wrapr", "extrr", "mk"],
    [
        (f"{nl}_{nr}_{c}", *map(staticmethod, params_funs[nl] + params_funs[nr] + (m,)))
        for nl, nr in params_pairs
        for c, m in params_mk
    ],
)
class TestAssign(TestCase):
    # constructs `assign` arguments (views, proxies, dicts) which have an "inner" and "outer" part
    # parameterized with a constructor and a layout of the inner part
    buildl: Callable[[Callable[[MethodLayout], AssignArg], MethodLayout], AssignArg]
    buildr: Callable[[Callable[[MethodLayout], AssignArg], MethodLayout], AssignArg]
    # constructs field specifications for `assign`, takes field specifications for the inner part
    wrapl: Callable[[AssignFields], AssignFields]
    wrapr: Callable[[AssignFields], AssignFields]
    # extracts the inner part of the structure
    extrl: Callable[[AssignArg], ArrayProxy]
    extrr: Callable[[AssignArg], ArrayProxy]
    # constructor, takes a layout
    mk: Callable[[MethodLayout], AssignArg]

    def test_wraps_eq(self):
        assert self.wrapl({}) == self.wrapr({})

    def test_rhs_exception(self):
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_ab), fields=AssignType.RHS))
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_ab), self.buildr(self.mk, layout_ac), fields=AssignType.RHS))

    def test_all_exception(self):
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_ab), fields=AssignType.ALL))
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_ab), self.buildr(self.mk, layout_a), fields=AssignType.ALL))
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_ab), self.buildr(self.mk, layout_ac), fields=AssignType.ALL))

    def test_missing_exception(self):
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_ab), fields=self.wrapl({"b"})))
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_ab), self.buildr(self.mk, layout_a), fields=self.wrapl({"b"})))
        with pytest.raises(KeyError):
            list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_a), fields=self.wrapl({"b"})))

    def test_wrong_bits(self):
        with pytest.raises(ValueError):
            list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_a_alt)))
        if self.mk != mkproxy:  # Arrays are troublesome and defeat some checks
            with pytest.raises(ValueError):
                list(assign(self.buildl(self.mk, layout_a), self.buildr(self.mk, layout_a_enum)))

    @parameterized.expand(
        [
            ("lhs", layout_a, layout_ab, AssignType.LHS),
            ("rhs", layout_ab, layout_a, AssignType.RHS),
            ("all", layout_a, layout_a, AssignType.ALL),
            ("common", layout_ab, layout_ac, AssignType.COMMON),
            ("set", layout_ab, layout_ab, {"a"}),
            ("list", layout_ab, layout_ab, ["a", "a"]),
        ]
    )
    def test_assign_a(self, name, layout1: MethodLayout, layout2: MethodLayout, atype: AssignType):
        lhs = self.buildl(self.mk, layout1)
        rhs = self.buildr(self.mk, layout2)
        alist = list(assign(lhs, rhs, fields=self.wrapl(atype)))
        assert len(alist) == 1
        self.assertIs_AP(alist[0].lhs, self.extrl(lhs).a)
        self.assertIs_AP(alist[0].rhs, self.extrr(rhs).a)

    def assertIs_AP(self, expr1, expr2):  # noqa: N802
        expr1 = Value.cast(expr1)
        expr2 = Value.cast(expr2)
        if isinstance(expr1, SwitchValue) and isinstance(expr2, SwitchValue):
            # new proxies are created on each index, structural equality is needed
            self.assertIs(expr1.test, expr2.test)
            assert len(expr1.cases) == len(expr2.cases)
            for (px, x), (py, y) in zip(expr1.cases, expr2.cases):
                self.assertEqual(px, py)
                self.assertIs_AP(x, y)
        elif isinstance(expr1, Slice) and isinstance(expr2, Slice):
            self.assertIs_AP(expr1.value, expr2.value)
            assert expr1.start == expr2.start
            assert expr1.stop == expr2.stop
        else:
            self.assertIs(expr1, expr2)
