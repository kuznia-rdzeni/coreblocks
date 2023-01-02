"""
Utilities for extracting dependency graphs from Amaranth designs.
"""

from abc import ABC
from collections import defaultdict
from typing import Literal, Optional, TYPE_CHECKING

from amaranth.hdl.ir import Elaboratable, Fragment
from .tracing import TracingFragment


if TYPE_CHECKING:
    # circular imports!
    from .core import Method, Transaction

    Owned = Method | Transaction
else:
    # this is insufficient for pyright, but whatever
    class Owned(ABC):
        name: str
        owner: Elaboratable


class OwnershipGraph:
    def __init__(self, root):
        self.class_counters: defaultdict[type, int] = defaultdict(int)
        self.names: dict[int, str] = {}
        self.hier: dict[int, str] = {}
        self.labels: dict[int, str] = {}
        self.graph: dict[int, list[int]] = {}
        self.edges: list[tuple[Owned, Owned, str]] = []
        self.owned: defaultdict[int, set[Owned]] = defaultdict(set)
        self.remember(root)

    def remember(self, owner: Elaboratable) -> int:
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

    def remember_field(self, owner_id: int, field: str, obj: Elaboratable):
        while hasattr(obj, "_tracing_original"):
            obj = obj._tracing_original
        obj_id = id(obj)
        if obj_id == owner_id or obj_id in self.labels:
            return
        self.labels[obj_id] = f"{field} {obj.__class__.__name__}"
        self.graph[owner_id].append(obj_id)
        self.remember(obj)

    def insert_node(self, obj: Owned):
        assert obj.owner is not None
        owner_id = self.remember(obj.owner)
        self.owned[owner_id].add(obj)

    def insert_edge(self, fr: Owned, to: Owned, direction: str = "->"):
        self.edges.append((fr, to, direction))

    def get_name(self, obj: Owned) -> str:
        assert obj.owner is not None
        owner_id = self.remember(obj.owner)
        return f"{self.names[owner_id]}_{obj.name}"

    def get_hier_name(self, obj: Owned) -> str:
        """
        Get hierarchical name.
        Might raise KeyError if not yet hierarchized.
        """
        assert obj.owner is not None
        owner_id = self.remember(obj.owner)
        name = f"{self.names[owner_id]}_{obj.name}"
        hier = self.hier[owner_id]
        return f"{hier}.{name}"

    def dump(self, fp, format: Literal["dot", "elk", "mermaid"]):
        dumper = getattr(self, "dump_" + format)
        dumper(fp)

    def dump_dot(self, fp, owner: Optional[int] = None, indent: str = ""):
        if owner is None:
            fp.write("digraph G {\n")
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_dot(fp, owner, indent)
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

    def dump_elk(self, fp, owner: Optional[int] = None, indent: str = ""):
        if owner is None:
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_elk(fp, owner, indent)
            return

        hier = self.hier.setdefault(owner, self.names[owner])

        subowners = self.graph[owner]
        del self.graph[owner]
        owned = self.owned[owner]
        fp.write(f"{indent}node {self.names[owner]} {{\n")
        fp.write(f"{indent}    considerModelOrder.components: INSIDE_PORT_SIDE_GROUPS\n")
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

    def dump_mermaid(self, fp, owner: Optional[int] = None, indent: str = ""):
        if owner is None:
            fp.write("flowchart TB\n")
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_mermaid(fp, owner, indent)
            for fr, to, direction in self.edges:
                caller_name = self.get_name(fr)
                callee_name = self.get_name(to)
                fp.write(f"{caller_name} {direction.replace('-', '--')} {callee_name}\n")
            return

        subowners = self.graph[owner]
        del self.graph[owner]
        indent += "    "
        owned = self.owned[owner]
        fp.write(f'{indent}subgraph {self.names[owner]}["{self.labels.get(owner, self.names[owner])}"]\n')
        for x in owned:
            fp.write(f'{indent}    {self.get_name(x)}["{x.name}"]\n')
        for subowner in subowners:
            if subowner in self.graph:
                self.dump_mermaid(fp, subowner, indent)
        fp.write(f"{indent}end\n")
