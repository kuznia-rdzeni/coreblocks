from collections import defaultdict
from enum import Enum
from amaranth import Elaboratable
from transactron import Method, TModule
from transactron.utils import DependencyContext
from transactron.lib.metrics import TaggedCounter
from coreblocks.interface.keys import InstructionTaggedCounterKey


__all__ = ["InstructionMetrics"]


class InstructionMetrics(Elaboratable):
    def elaborate(self, platform):
        m = TModule()

        dm = DependencyContext.get()
        incr_methods = dm.get_dependency(InstructionTaggedCounterKey())

        incr_methods_by_tag_type: defaultdict[tuple[str, type[Enum]], list[Method]] = defaultdict(list)
        for fu_name, method in incr_methods:
            tag_type = method.layout_in.members["tag"]
            assert isinstance(tag_type, type) and issubclass(tag_type, Enum)
            incr_methods_by_tag_type[(fu_name, tag_type)].append(method)

        for (fu_name, tag_type), methods in incr_methods_by_tag_type.items():
            m.submodules[f"counter_{fu_name}_{tag_type.__qualname__}"] = counter = TaggedCounter(
                f"backend.fu.{fu_name}.{tag_type.__qualname__}",
                f"Counts of instructions executed by {fu_name} for tag {tag_type.__qualname__}",
                tags=tag_type,
                ways=len(methods),
            )

            for incr_method, method in zip(counter.incr, methods):
                method.provide(incr_method)

        return m
