"""
Utilities for extracting dependencies from Amaranth.
"""

import warnings

from amaranth.hdl import Elaboratable, Fragment, Instance
from amaranth.hdl._xfrm import FragmentTransformer
from amaranth.hdl import _dsl, _ir, _mem, _xfrm
from amaranth.lib import memory  # type: ignore
from amaranth_types import SrcLoc
from transactron.utils import HasElaborate
from . import core


# generic tuple because of aggressive monkey-patching
modules_with_fragment: tuple = core, _ir, _dsl, _mem, _xfrm
# List of Fragment subclasses which should be patched to inherit from TracingFragment.
# The first element of the tuple is a subclass name to patch, and the second element
# of the tuple is tuple with modules in which the patched subclass should be installed.
fragment_subclasses_to_patch = [("MemoryInstance", (memory, _mem, _xfrm))]

DIAGNOSTICS = False
orig_on_fragment = FragmentTransformer.on_fragment


class TracingEnabler:
    def __enter__(self):
        self.orig_fragment_get = Fragment.get
        self.orig_on_fragment = FragmentTransformer.on_fragment
        self.orig_fragment_class = _ir.Fragment
        self.orig_instance_class = _ir.Instance
        self.orig_patched_fragment_subclasses = []
        Fragment.get = TracingFragment.get
        FragmentTransformer.on_fragment = TracingFragmentTransformer.on_fragment
        for mod in modules_with_fragment:
            mod.Fragment = TracingFragment
            mod.Instance = TracingInstance
        for class_name, modules in fragment_subclasses_to_patch:
            orig_fragment_subclass = getattr(modules[0], class_name)
            # `type` is used to declare new class dynamicaly. There is passed `orig_fragment_subclass` as a first
            # base class to allow `super()` to work. Calls to `super` without arguments are syntax sugar and are
            # extended on compile/interpretation (not execution!) phase to the `super(OriginalClass, self)`,
            # so they are hardcoded on execution time to look for the original class
            # (see: https://docs.python.org/3/library/functions.html#super).
            # This cause that OriginalClass has to be in `__mro__` of the newly created class, because else an
            # TypeError will be raised (see: https://stackoverflow.com/a/40819403). Adding OriginalClass to the
            # bases of patched class allows us to fix the TypeError. Everything works correctly because `super`
            # starts search of `__mro__` from the class right after the first argument. In our case the first
            # checked class will be `TracingFragment` as we want.
            newclass = type(
                class_name,
                (
                    orig_fragment_subclass,
                    TracingFragment,
                ),
                dict(orig_fragment_subclass.__dict__),
            )
            for mod in modules:
                setattr(mod, class_name, newclass)
            self.orig_patched_fragment_subclasses.append((class_name, orig_fragment_subclass, modules))

    def __exit__(self, tp, val, tb):
        Fragment.get = self.orig_fragment_get
        FragmentTransformer.on_fragment = self.orig_on_fragment
        for mod in modules_with_fragment:
            mod.Fragment = self.orig_fragment_class
            mod.Instance = self.orig_instance_class
        for class_name, orig_fragment_subclass, modules in self.orig_patched_fragment_subclasses:
            for mod in modules:
                setattr(mod, class_name, orig_fragment_subclass)


class TracingFragmentTransformer(FragmentTransformer):
    def on_fragment(self: FragmentTransformer, fragment):
        ret = orig_on_fragment(self, fragment)
        ret._tracing_original = fragment
        fragment._elaborated = ret
        return ret


class TracingFragment(Fragment):
    _tracing_original: Elaboratable
    subfragments: list[tuple[Elaboratable, str, SrcLoc]]

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
    def get(obj: HasElaborate, platform) -> "TracingFragment":
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
                    obj._MustUse__used = True  # type: ignore
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
                new_obj._tracing_original = obj  # type: ignore
                obj._elaborated = new_obj  # type: ignore

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
