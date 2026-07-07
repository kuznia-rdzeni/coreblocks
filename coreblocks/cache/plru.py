from amaranth import *

from transactron import Method, Methods, TModule, def_method, def_methods
from transactron.utils.transactron_helpers import make_layout

__all__ = ["TreePLRU"]


class TreePLRU(Elaboratable):
    """Tree-based pseudo-LRU replacement state over a power-of-two number of ways.

    Tree-PLRU keeps one bit per internal node of a balanced binary tree. For a cache
    with N ways, it requires exactly N - 1 bits. Each internal node indicates which
    side was accessed less recently (0 - the left side).

    To find the least recently used item, we traverse down the tree from the root node,
    following the directions indicated by each bit.

    When accessing an item, the bits along its specific path are flipped to point in
    the opposite direction, so it is not selected for subsequent evictions.

    Methods
    -------
    get_victim: Method (nonexclusive)
        Returns the way to replace.
    touch: Methods
        Each method marks its ``way`` argument as most-recently-used. Touches are applied
        in port order, so a higher-indexed port wins.
    """

    def __init__(self, ways: int, touch_ports: int = 1):
        assert ways >= 2 and ways & (ways - 1) == 0, "TreePLRU ways must be a power of two"

        self.ways = ways
        self.ways_log = (ways - 1).bit_length()

        way_layout = make_layout(("way", range(ways)))
        self.get_victim = Method(o=way_layout)
        self.touch = Methods(touch_ports, i=way_layout)

    def elaborate(self, platform):
        m = TModule()

        tree = Signal(self.ways - 1)

        def victim_of(node: int, level: int) -> Value:
            if level == self.ways_log:
                return C(0, 0)
            bit = tree[node]
            left = victim_of(2 * node + 1, level + 1)
            right = victim_of(2 * node + 2, level + 1)
            return Cat(Mux(bit, right, left), bit)

        @def_method(m, self.get_victim, nonexclusive=True)
        def _():
            return {"way": victim_of(0, 0)}

        @def_methods(m, self.touch)
        def _(k: int, way: Value):
            pass

        def apply_touch(cur: dict[int, Value], valid: Value, way: Value) -> dict[int, Value]:
            new = dict(cur)

            def walk(node: int, level: int, on_path: Value):
                if level == self.ways_log:
                    return
                direction = way[self.ways_log - 1 - level]
                new[node] = Mux(valid & on_path, ~direction, cur[node])
                walk(2 * node + 1, level + 1, on_path & ~direction)
                walk(2 * node + 2, level + 1, on_path & direction)

            walk(0, 0, C(1, 1))
            return new

        # Apply each touch in port order; a higher-indexed port wins on shared nodes.
        state = {node: tree[node] for node in range(self.ways - 1)}
        for port in self.touch:
            state = apply_touch(state, port.run, port.data_in.way)

        m.d.sync += tree.eq(Cat(state[node] for node in range(self.ways - 1)))

        return m
