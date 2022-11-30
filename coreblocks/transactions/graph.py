"""
Utilities for extracting dependency graphs from Amaranth designs.
"""

from collections import defaultdict

from amaranth.hdl.ir import Elaboratable, Fragment
from .tracing import TracingFragment


class OwnershipGraph:
    def __init__(self, root):
        self.class_counters: defaultdict[type, int] = defaultdict(int)
        self.names: dict[int, str] = {}
        self.hier: dict[int, str] = {}
        self.labels: dict[int, str] = {}
        self.graph: dict[int, list[object]] = {}
        self.edges: list[tuple[object, object, str]] = []
        self.owned: defaultdict[int, set] = defaultdict(set)
        self.remember(root)

    def remember(self, owner) -> int:
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
                    assert isinstance(owner, TracingFragment)
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

    def insert_node(self, obj):
        owner_id = self.remember(obj.owner)
        self.owned[owner_id].add(obj)

    def insert_edge(self, fr, to, direction="->"):
        self.edges.append((fr, to, direction))

    def get_name(self, obj) -> str:
        owner_id = self.remember(obj.owner)
        return f"{self.names[owner_id]}_{obj.name}"

    def get_hier_name(self, obj) -> str:
        """
        Get hierarchical name.
        Might raise KeyError if not yet hierarchized.
        """
        owner_id = self.remember(obj.owner)
        name = f"{self.names[owner_id]}_{obj.name}"
        hier = self.hier[owner_id]
        return f"{hier}.{name}"

    def dump(self, fp, format):
        dumper = getattr(self, "dump_" + format)
        dumper(fp)

    def dump_dot(self, fp, owner=None, indent=""):
        if owner is None:
            fp.write("digraph G {\n")
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_dot(fp, owner)
            for fr, to, direction in self.edges:
                caller_name = self.get_name(fr)
                callee_name = self.get_name(to)
                fp.write(f"{caller_name} {direction} {callee_name}\n")
            fp.write("}\n")
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

        # reverse iteration so that deleting works
        for i, (fr, to, direction) in reversed(list(enumerate(self.edges))):
            try:
                caller_name = self.get_hier_name(fr)
                callee_name = self.get_hier_name(to)
            except KeyError:
                continue

            # only output edges belonging here
            if caller_name[: len(hier)] == callee_name[: len(hier)] == hier:
                caller_name = caller_name[len(hier) + 1 :]
                callee_name = callee_name[len(hier) + 1 :]
                del self.edges[i]
                fp.write(f"{indent}    edge {caller_name} {direction} {callee_name}\n")

        fp.write(f"{indent}}}\n")
