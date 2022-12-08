"""
Utilities for extracting dependencies from Amaranth.
"""

import warnings

from amaranth.hdl.ir import Elaboratable, Fragment, Instance
from amaranth.hdl.xfrm import FragmentTransformer
from amaranth.hdl import dsl, ir, mem, xfrm
from . import core


# generic tuple because of aggressive monkey-patching
modules_with_fragment: tuple = core, ir, dsl, mem, xfrm

DIAGNOSTICS = False
orig_on_fragment = FragmentTransformer.on_fragment


class TracingEnabler:
    def __enter__(self):
        self.orig_fragment_get = Fragment.get
        self.orig_on_fragment = FragmentTransformer.on_fragment
        self.orig_fragment_class = ir.Fragment
        self.orig_instance_class = ir.Instance
        Fragment.get = TracingFragment.get
        FragmentTransformer.on_fragment = TracingFragmentTransformer.on_fragment
        for mod in modules_with_fragment:
            mod.Fragment = TracingFragment
            mod.Instance = TracingInstance

    def __exit__(self, tp, val, tb):
        Fragment.get = self.orig_fragment_get
        FragmentTransformer.on_fragment = self.orig_on_fragment
        for mod in modules_with_fragment:
            mod.Fragment = self.orig_fragment_class
            mod.Instance = self.orig_instance_class


class TracingFragmentTransformer(FragmentTransformer):
    def on_fragment(self: FragmentTransformer, fragment):
        ret = orig_on_fragment(self, fragment)
        ret._tracing_original = fragment
        fragment._elaborated = ret
        return ret


class TracingFragment(Fragment):
    _tracing_original: Elaboratable
    subfragments: list[tuple[Elaboratable, str]]

    if DIAGNOSTICS:

        def __init__(self, *args, **kwargs):
            import sys
            import traceback

            self.created = traceback.format_stack(sys._getframe(1))
            super().__init__(*args, **kwargs)

        def __del__(self):
            if not hasattr(self, "_tracing_original"):
                print("Missing tracing hook:")
                for line in self.created:
                    print(line, end="")

    @staticmethod
    def get(obj: Elaboratable, platform) -> "TracingFragment":
        """
        This function code is based on Amaranth, which originally loses all information.
        It was too difficult to hook into, so this has to be a near-exact copy.

        Relevant copyrights apply.
        """
        with TracingEnabler():
            code = None
            old_obj = None
            while True:
                if isinstance(obj, TracingFragment):
                    return obj
                elif isinstance(obj, Fragment):
                    raise NotImplementedError(f"Monkey-patching missed some Fragment in {old_obj}.elaborate()?")
                # This is literally taken from Amaranth {{
                elif isinstance(obj, Elaboratable):
                    code = obj.elaborate.__code__
                    obj._MustUse__used = True
                    new_obj = obj.elaborate(platform)
                elif hasattr(obj, "elaborate"):
                    warnings.warn(
                        message="Class {!r} is an elaboratable that does not explicitly inherit from "
                        "Elaboratable; doing so would improve diagnostics".format(type(obj)),
                        category=RuntimeWarning,
                        stacklevel=2,
                    )
                    code = obj.elaborate.__code__
                    new_obj = obj.elaborate(platform)
                else:
                    raise AttributeError("Object {!r} cannot be elaborated".format(obj))
                if new_obj is obj:
                    raise RecursionError("Object {!r} elaborates to itself".format(obj))
                if new_obj is None and code is not None:
                    warnings.warn_explicit(
                        message=".elaborate() returned None; missing return statement?",
                        category=UserWarning,
                        filename=code.co_filename,
                        lineno=code.co_firstlineno,
                    )
                # }} (taken from Amaranth)
                new_obj._tracing_original = obj
                obj._elaborated = new_obj

                old_obj = obj
                obj = new_obj

    def prepare(self, *args, **kwargs) -> "TracingFragment":
        with TracingEnabler():
            ret = super().prepare(*args, **kwargs)
            ret._tracing_original = self
            self._elaborated = ret
            return ret


class TracingInstance(Instance, TracingFragment):
    _tracing_original: Elaboratable
    get = TracingFragment.get
