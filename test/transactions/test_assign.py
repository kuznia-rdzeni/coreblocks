from typing import Callable
from amaranth import *
from amaranth.hdl.ast import ArrayProxy

from coreblocks.utils._typing import LayoutLike
from coreblocks.utils.utils import AssignLHS, AssignType, AssignFields, assign

from unittest import TestCase
from parameterized import parameterized_class, parameterized


layout_a = [("a", 1)]
layout_ab = [("a", 1), ("b", 2)]
layout_ac = [("a", 1), ("c", 3)]
layout_a_alt = [("a", 2)]

params_fgh = [
    ("normal", lambda c, l: c(l), lambda x: x, lambda r: r),
    ("rec", lambda c, l: c([("x", l)]), lambda x: {"x": x}, lambda r: r.x),
    ("dict", lambda c, l: {"x": c(l)}, lambda x: {"x": x}, lambda r: r["x"]),
]


def mkproxy(layout):
    arr = Array([Record(layout) for _ in range(4)])
    sig = Signal(2)
    return arr[sig]


params_c = [
    ("rec", Record),
    ("proxy", mkproxy),
]


@parameterized_class(["name", "f", "g", "h", "constr", "c"], [t + u for t in params_fgh for u in params_c])
class TestAssign(TestCase):
    # constructs `assign` arguments (records, proxies, dicts) which have an "inner" and "outer" part
    # parameterized with a Record-like constructor and a layout of the inner part
    f: Callable[[Callable[[LayoutLike], AssignLHS], LayoutLike], AssignLHS]
    # constructs field specifications for `assign`, takes field specifications for the inner part
    g: Callable[[AssignFields], AssignFields]
    # extracts the inner part of the structure
    h: Callable[[AssignLHS], Record | ArrayProxy]
    # Record-like constructor, takes a record layout
    c: Callable[[LayoutLike], AssignLHS]

    def test_rhs_exception(self):
        f = self.__class__.f
        c = self.__class__.c
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_a), f(c, layout_ab), fields=AssignType.RHS))
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_ab), f(c, layout_ac), fields=AssignType.RHS))

    def test_all_exception(self):
        f = self.__class__.f
        c = self.__class__.c
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_a), f(c, layout_ab), fields=AssignType.ALL))
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_ab), f(c, layout_a), fields=AssignType.ALL))
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_ab), f(c, layout_ac), fields=AssignType.ALL))

    def test_missing_exception(self):
        f = self.__class__.f
        g = self.__class__.g
        c = self.__class__.c
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_a), f(c, layout_ab), fields=g({"b"})))
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_ab), f(c, layout_a), fields=g({"b"})))
        with self.assertRaises(KeyError):
            list(assign(f(c, layout_a), f(c, layout_a), fields=g({"b"})))

    def test_wrong_bits(self):
        f = self.__class__.f
        c = self.__class__.c
        with self.assertRaises(ValueError):
            list(assign(f(c, layout_a), f(c, layout_a_alt)))

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
        f = self.__class__.f
        g = self.__class__.g
        h = self.__class__.h
        c = self.__class__.c
        lhs = f(c, layout1)
        rhs = f(c, layout2)
        alist = list(assign(lhs, rhs, fields=g(atype)))
        self.assertEqual(len(alist), 1)
        self.assertIs_AP(alist[0].lhs, h(lhs).a)
        self.assertIs_AP(alist[0].rhs, h(rhs).a)

    def assertIs_AP(self, expr1, expr2):  # noqa: N802
        if isinstance(expr1, ArrayProxy) and isinstance(expr2, ArrayProxy):
            # new proxies are created on each index, structural equality is needed
            self.assertIs(expr1.index, expr2.index)
            self.assertEqual(len(expr1.elems), len(expr2.elems))
            for x, y in zip(expr1.elems, expr2.elems):
                self.assertIs_AP(x, y)
        else:
            self.assertIs(expr1, expr2)
