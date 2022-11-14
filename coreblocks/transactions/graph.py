"""
Utilities for extracting dependency graphs from Amaranth designs.
"""

import warnings
from collections import defaultdict

from amaranth.hdl.ir import Elaboratable, Fragment, Instance
from amaranth.hdl.xfrm import FragmentTransformer
from amaranth.hdl import dsl, ir, mem, xfrm
from . import core


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
        for mod in core, ir, dsl, mem, xfrm:
            mod.Fragment = TracingFragment
            mod.Instance = TracingInstance

    def __exit__(self, tp, val, tb):
        Fragment.get = self.orig_fragment_get
        FragmentTransformer.on_fragment = self.orig_on_fragment
        for mod in core, ir, dsl, mem, xfrm:
            mod.Fragment = self.orig_fragment_class
            mod.Instance = self.orig_instance_class


class TracingFragmentTransformer(FragmentTransformer):
    def on_fragment(self, fragment):
        ret = orig_on_fragment(self, fragment)
        ret._tracing_original = fragment
        fragment._elaborated = ret
        return ret


class TracingFragment(Fragment):
    _tracing_original: Elaboratable

    if DIAGNOSTICS:

        def __init__(self, *args, **kwargs) -> "TracingFragment":
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
        with TracingEnabler():
            code = None
            old_obj = None
            while True:
                if isinstance(obj, TracingFragment):
                    return obj
                elif isinstance(obj, Fragment):
                    raise NotImplementedError(f"Some Fragment missed in {old_obj}?")
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


class OwnershipGraph:
    def __init__(self, root):
        self.class_counters = defaultdict(int)
        self.names = {}
        self.hier = {}
        self.labels = {}
        self.graph = {}
        self.owned = defaultdict(set)
        self.remember(root)

    def remember(self, owner):
        while hasattr(owner, "_tracing_original"):
            owner = owner._tracing_original
        owner_id = id(owner)
        if owner_id not in self.names:
            tp = type(owner)
            count = self.class_counters[tp]
            self.class_counters[tp] = count + 1

            name = tp.__name__
            if count:
                name += str(count)
            self.names[owner_id] = name
            self.graph[owner_id] = []
            while True:
                for field, obj in vars(owner).items():
                    if isinstance(obj, Elaboratable) and not field.startswith("_"):
                        self.remember_field(owner_id, field, obj)
                if isinstance(owner, Fragment):
                    for obj, field in owner.subfragments:
                        self.remember_field(owner_id, field, obj)
                try:
                    owner = owner._elaborated
                except AttributeError:
                    break
        return owner_id

    def remember_field(self, owner_id, field, obj):
        while hasattr(obj, "_tracing_original"):
            obj = obj._tracing_original
        obj_id = id(obj)
        if obj_id == owner_id or obj_id in self.labels:
            return
        self.labels[obj_id] = f"{field} {obj.__class__.__name__}"
        self.graph[owner_id].append(obj_id)
        self.remember(obj)

    def get_name(self, obj, add=False):
        owner_id = self.remember(obj.owner)
        if add:
            self.owned[owner_id].add(obj)
        return f"{self.names[owner_id]}_{obj.name}"

    def get_hier_name(self, obj):
        owner_id = self.remember(obj.owner)
        name = f"{self.names[owner_id]}_{obj.name}"
        hier = self.hier[owner_id]
        return f"{hier}.{name}"

    def dump_dot(self, fp, owner=None, indent=""):
        if owner is None:
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_dot(fp, owner)
            return

        subowners = self.graph[owner]
        del self.graph[owner]
        indent += "    "
        owned = self.owned[owner]
        fp.write(f"{indent}subgraph cluster_{self.names[owner]} {{\n")
        fp.write(f'{indent}    label="{self.labels.get(owner, self.names[owner])}";\n')
        for x in owned:
            fp.write(f'{indent}    {self.get_name(x)} [label="{x.name}"];\n')
        for subowner in subowners:
            if subowner in self.graph:
                self.dump_dot(fp, subowner, indent)
        fp.write(f"{indent}}}\n")

    def dump_elk(self, fp, owner=None, indent=""):
        if owner is None:
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_elk(fp, owner)
            return

        hier = self.hier.setdefault(owner, self.names[owner])

        subowners = self.graph[owner]
        del self.graph[owner]
        owned = self.owned[owner]
        fp.write(f"{indent}node {self.names[owner]} {{\n")
        fp.write(f'{indent}    label "{self.labels.get(owner, self.names[owner])}"\n')
        for x in owned:
            fp.write(f'{indent}    node {self.get_name(x)} {{ label "{x.name}" }}\n')
        for subowner in subowners:
            if subowner in self.graph:
                self.hier[subowner] = f"{hier}.{self.names[subowner]}"
                self.dump_elk(fp, subowner, indent + "    ")
        fp.write(f"{indent}}}\n")
