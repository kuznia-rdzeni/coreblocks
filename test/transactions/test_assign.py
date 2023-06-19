from typing import Callable
from amaranth import *
from amaranth.lib import data
from amaranth.hdl.ast import ArrayProxy, Slice

from coreblocks.utils._typing import LayoutLike
from coreblocks.utils.utils import AssignArg, AssignType, AssignFields, assign

from unittest import TestCase
from parameterized import parameterized_class, parameterized


layout_a = [("a", 1)]
layout_ab = [("a", 1), ("b", 2)]
layout_ac = [("a", 1), ("c", 3)]
layout_a_alt = [("a", 2)]

params_build_wrap_extr = [
    ("normal", lambda mk, lay: mk(lay), lambda x: x, lambda r: r),
    ("rec", lambda mk, lay: mk([("x", lay)]), lambda x: {"x": x}, lambda r: r.x),
    ("dict", lambda mk, lay: {"x": mk(lay)}, lambda x: {"x": x}, lambda r: r["x"]),
]


def mkproxy(layout):
    arr = Array([Record(layout) for _ in range(4)])
    sig = Signal(2)
    return arr[sig]


def reclayout2datalayout(layout):
    if not isinstance(layout, list):
        return layout
    return data.StructLayout({k: reclayout2datalayout(lay) for k, lay in layout})


def mkstruct(layout):
    return Signal(reclayout2datalayout(layout))


params_mk = [
    ("rec", Record),
    ("proxy", mkproxy),
    ("struct", mkstruct),
]


@parameterized_class(
    ["name", "build", "wrap", "extr", "constr", "mk"],
    [
        (n, *map(staticmethod, (b, w, e)), c, staticmethod(m))
        for n, b, w, e in params_build_wrap_extr
        for c, m in params_mk
    ],
)
class TestAssign(TestCase):
    # constructs `assign` arguments (records, proxies, dicts) which have an "inner" and "outer" part
    # parameterized with a Record-like constructor and a layout of the inner part
    build: Callable[[Callable[[LayoutLike], AssignArg], LayoutLike], AssignArg]
    # constructs field specifications for `assign`, takes field specifications for the inner part
    wrap: Callable[[AssignFields], AssignFields]
    # extracts the inner part of the structure
    extr: Callable[[AssignArg], Record | ArrayProxy]
    # Record-like constructor, takes a record layout
    mk: Callable[[LayoutLike], AssignArg]

    def test_rhs_exception(self):
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_a), self.build(self.mk, layout_ab), fields=AssignType.RHS))
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_ab), self.build(self.mk, layout_ac), fields=AssignType.RHS))

    def test_all_exception(self):
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_a), self.build(self.mk, layout_ab), fields=AssignType.ALL))
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_ab), self.build(self.mk, layout_a), fields=AssignType.ALL))
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_ab), self.build(self.mk, layout_ac), fields=AssignType.ALL))

    def test_missing_exception(self):
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_a), self.build(self.mk, layout_ab), fields=self.wrap({"b"})))
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_ab), self.build(self.mk, layout_a), fields=self.wrap({"b"})))
        with self.assertRaises(KeyError):
            list(assign(self.build(self.mk, layout_a), self.build(self.mk, layout_a), fields=self.wrap({"b"})))

    def test_wrong_bits(self):
        with self.assertRaises(ValueError):
            list(assign(self.build(self.mk, layout_a), self.build(self.mk, layout_a_alt)))

    @parameterized.expand(
        [
            ("rhs", layout_ab, layout_a, AssignType.RHS),
            ("all", layout_a, layout_a, AssignType.ALL),
            ("common", layout_ab, layout_ac, AssignType.COMMON),
            ("set", layout_ab, layout_ab, {"a"}),
            ("list", layout_ab, layout_ab, ["a", "a"]),
        ]
    )
    def test_assign_a(self, name, layout1: LayoutLike, layout2: LayoutLike, atype: AssignType):
        lhs = self.build(self.mk, layout1)
        rhs = self.build(self.mk, layout2)
        alist = list(assign(lhs, rhs, fields=self.wrap(atype)))
        self.assertEqual(len(alist), 1)
        self.assertIs_AP(alist[0].lhs, self.extr(lhs).a)
        self.assertIs_AP(alist[0].rhs, self.extr(rhs).a)

    def assertIs_AP(self, expr1, expr2):  # noqa: N802
        if isinstance(expr1, ArrayProxy) and isinstance(expr2, ArrayProxy):
            # new proxies are created on each index, structural equality is needed
            self.assertIs(expr1.index, expr2.index)
            self.assertEqual(len(expr1.elems), len(expr2.elems))
            for x, y in zip(expr1.elems, expr2.elems):
                self.assertIs_AP(x, y)
        elif isinstance(expr1, Slice) and isinstance(expr2, Slice):
            self.assertIs_AP(expr1.value, expr2.value)
            self.assertEqual(expr1.start, expr2.start)
            self.assertEqual(expr1.stop, expr2.stop)
        else:
            self.assertIs(expr1, expr2)
