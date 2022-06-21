from typing import Callable
from amaranth import *

from coreblocks._typing import LayoutLike
from coreblocks.utils import AssignType, AssignFields, assign

from unittest import TestCase
from parameterized import parameterized_class, parameterized


layout_a = [("a", 1)]
layout_ab = [("a", 1), ("b", 2)]
layout_ac = [("a", 1), ("c", 3)]
layout_a_alt = [("a", 2)]


@parameterized_class(
    ["name", "f", "g", "h"],
    [
        ("normal", lambda l: l, lambda x: x, lambda x: x),
        ("rec", lambda l: [("x", l)], lambda x: {"x": x}, lambda x: x.x),
    ],
)
class TestAssign(TestCase):
    f: Callable[[LayoutLike], LayoutLike]
    g: Callable[[AssignFields], AssignFields]
    h: Callable[[Record], Record]

    def test_rhs_exception(self):
        f = self.__class__.f
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_a)), Record(f(layout_ab)), fields=AssignType.RHS))
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_ab)), Record(f(layout_ac)), fields=AssignType.RHS))

    def test_all_exception(self):
        f = self.__class__.f
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_a)), Record(f(layout_ab)), fields=AssignType.ALL))
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_ab)), Record(f(layout_a)), fields=AssignType.ALL))
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_ab)), Record(f(layout_ac)), fields=AssignType.ALL))

    def test_missing_exception(self):
        f = self.__class__.f
        g = self.__class__.g
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_a)), Record(f(layout_ab)), fields=g({"b"})))
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_ab)), Record(f(layout_a)), fields=g({"b"})))
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_a)), Record(f(layout_a)), fields=g({"b"})))

    def test_wrong_bits(self):
        f = self.__class__.f
        with self.assertRaises(ValueError):
            list(assign(Record(f(layout_a)), Record(f(layout_a_alt))))

    @parameterized.expand(
        [
            (layout_ab, layout_a, AssignType.RHS),
            (layout_a, layout_a, AssignType.ALL),
            (layout_ab, layout_ac, AssignType.COMMON),
        ]
    )
    def test_assign_a(self, layout1: LayoutLike, layout2: LayoutLike, atype: AssignType):
        f = self.__class__.f
        h = self.__class__.h
        lhs = Record(f(layout1))
        rhs = Record(f(layout2))
        alist = list(assign(lhs, rhs, fields=atype))
        self.assertEqual(len(alist), 1)
        self.assertIs(alist[0].lhs, h(lhs).a)
        self.assertIs(alist[0].rhs, h(rhs).a)
