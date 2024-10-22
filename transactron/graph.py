"""
Utilities for extracting dependency graphs from Amaranth designs.
"""

from enum import IntFlag
from collections import defaultdict
from typing import Literal, Optional, Protocol

from amaranth import Elaboratable, Fragment
from .tracing import TracingFragment


class Owned(Protocol):
    name: str
    owner: Optional[Elaboratable]


class Direction(IntFlag):
    NONE = 0
    IN = 1
    OUT = 2
    INOUT = 3


class OwnershipGraph:
    mermaid_direction = ["---", "-->", "<--", "<-->"]

    def __init__(self, root):
        self.class_counters: defaultdict[type, int] = defaultdict(int)
        self.owned_counters: defaultdict[tuple[int, str], int] = defaultdict(int)
        self.names: dict[int, str] = {}
        self.owned_names: dict[int, str] = {}
        self.hier: dict[int, str] = {}
        self.labels: dict[int, str] = {}
        self.graph: dict[int, list[int]] = {}
        self.edges: list[tuple[Owned, Owned, Direction]] = []
        self.owned: defaultdict[int, set[Owned]] = defaultdict(set)
        self.stray: set[int] = set()
        self.remember(root)

    def remember(self, owner: Elaboratable) -> int:
        while hasattr(owner, "_tracing_original"):
            owner = owner._tracing_original  # type: ignore
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
                    for obj, field, _ in owner.subfragments:
                        self.remember_field(owner_id, field, obj)
                try:
                    owner = owner._elaborated  # type: ignore
                except AttributeError:
                    break
        return owner_id

    def remember_field(self, owner_id: int, field: str, obj: Elaboratable):
        while hasattr(obj, "_tracing_original"):
            obj = obj._tracing_original  # type: ignore
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

    def insert_edge(self, fr: Owned, to: Owned, direction: Direction = Direction.OUT):
        self.edges.append((fr, to, direction))

    def get_name(self, obj: Owned) -> str:
        assert obj.owner is not None
        obj_id = id(obj)
        name = self.owned_names.get(obj_id)
        if name is not None:
            return name
        owner_id = self.remember(obj.owner)
        count = self.owned_counters[(owner_id, obj.name)]
        self.owned_counters[(owner_id, obj.name)] = count + 1
        suffix = str(count) if count else ""
        name = self.owned_names[obj_id] = f"{self.names[owner_id]}_{obj.name}{suffix}"
        return name

    def get_hier_name(self, obj: Owned) -> str:
        """
        Get hierarchical name.
        Might raise KeyError if not yet hierarchized.
        """
        name = self.get_name(obj)
        owner_id = id(obj.owner)
        hier = self.hier[owner_id]
        return f"{hier}.{name}"

    def prune(self, owner: Optional[int] = None):
        """
        Mark all empty subgraphs.
        """
        if owner is None:
            backup = self.graph.copy()
            for owner in self.names:
                if owner not in self.labels:
                    self.prune(owner)
            self.graph = backup
            return

        subowners = self.graph.pop(owner)
        flag = bool(self.owned[owner])
        for subowner in subowners:
            if subowner in self.graph:
                flag |= self.prune(subowner)

        if not flag:
            self.stray.add(owner)

        return flag

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
                if direction == Direction.OUT:
                    fr, to = to, fr

                caller_name = self.get_name(fr)
                callee_name = self.get_name(to)
                fp.write(f"{caller_name} -> {callee_name}\n")
            fp.write("}\n")
            return

        subowners = self.graph.pop(owner)
        if owner in self.stray:
            return
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
            fp.write(f"{indent}hierarchyHandling: INCLUDE_CHILDREN\n")
            fp.write(f"{indent}elk.direction: DOWN\n")
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_elk(fp, owner, indent)
            return

        hier = self.hier.setdefault(owner, self.names[owner])

        subowners = self.graph.pop(owner)
        if owner in self.stray:
            return
        owned = self.owned[owner]
        fp.write(f"{indent}node {self.names[owner]} {{\n")
        fp.write(f"{indent}    considerModelOrder.components: INSIDE_PORT_SIDE_GROUPS\n")
        fp.write(f'{indent}    nodeSize.constraints: "[PORTS, PORT_LABELS, MINIMUM_SIZE]"\n')
        fp.write(f'{indent}    nodeLabels.placement: "[H_LEFT, V_TOP, OUTSIDE]"\n')
        fp.write(f'{indent}    portLabels.placement: "[INSIDE]"\n')
        fp.write(f"{indent}    feedbackEdges: true\n")
        fp.write(f'{indent}    label "{self.labels.get(owner, self.names[owner])}"\n')
        for x in owned:
            if x.__class__.__name__ == "Method":
                fp.write(f'{indent}    port {self.get_name(x)} {{ label "{x.name}" }}\n')
            else:
                fp.write(f"{indent}    node {self.get_name(x)} {{\n")
                fp.write(f'{indent}        nodeSize.constraints: "[NODE_LABELS, MINIMUM_SIZE]"\n')
                fp.write(f'{indent}        nodeLabels.placement: "[H_CENTER, V_CENTER, INSIDE]"\n')
                fp.write(f'{indent}        label "{x.name}"\n')
                fp.write(f"{indent}    }}\n")
        for subowner in subowners:
            if subowner in self.graph:
                self.hier[subowner] = f"{hier}.{self.names[subowner]}"
                self.dump_elk(fp, subowner, indent + "    ")

        # reverse iteration so that deleting works
        for i, (fr, to, direction) in reversed(list(enumerate(self.edges))):
            if direction == Direction.OUT:
                fr, to = to, fr

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
                fp.write(f"{indent}    edge {caller_name} -> {callee_name}\n")

        fp.write(f"{indent}}}\n")

    def dump_mermaid(self, fp, owner: Optional[int] = None, indent: str = ""):
        if owner is None:
            fp.write("flowchart TB\n")
            for owner in self.names:
                if owner not in self.labels:
                    self.dump_mermaid(fp, owner, indent)
            for fr, to, direction in self.edges:
                if direction == Direction.OUT:
                    fr, to, direction = to, fr, Direction.IN

                caller_name = self.get_name(fr)
                callee_name = self.get_name(to)
                fp.write(f"{caller_name} {self.mermaid_direction[direction]} {callee_name}\n")
            return

        subowners = self.graph.pop(owner)
        if owner in self.stray:
            return
        indent += "    "
        owned = self.owned[owner]
        fp.write(f'{indent}subgraph {self.names[owner]}["{self.labels.get(owner, self.names[owner])}"]\n')
        for x in owned:
            fp.write(f'{indent}    {self.get_name(x)}["{x.name}"]\n')
        for subowner in subowners:
            if subowner in self.graph:
                self.dump_mermaid(fp, subowner, indent)
        fp.write(f"{indent}end\n")
