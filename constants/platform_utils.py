from collections.abc import Iterable
from itertools import chain
from typing import Protocol
from amaranth import *
from amaranth.build.dsl import Subsignal
from amaranth.build import Attrs, Resource, Pins
from amaranth.lib.wiring import Signature, Flow

__all__ = ["PinManager", "ResourceBuilder", "signature_resources", "append_resources"]


def iterate_members(signature: Signature):
    for hier_name, member in signature.members.flatten():
        if not member.is_port:
            continue
        name = "__".join(str(x) for x in hier_name)
        yield name, member


def SignatureResource(  # noqa: N802
    *args, signature: Signature, default_name: str, conn=None, attrs: Attrs | None = None, **pinargs: str
):
    io = []

    for name, member in iterate_members(signature):
        dir = "i" if member.flow == Flow.In else "o"
        io.append(Subsignal(name, Pins(pinargs[name], dir=dir, conn=conn)))
    if attrs is not None:
        io.append(attrs)
    return Resource.family(*args, default_name=default_name, ios=io)


class PinManager:
    def __init__(self, pins: Iterable[str]):
        self.pin_bag = list(pins)

    def p(self, count: int = 1):
        return " ".join([self.pin_bag.pop() for _ in range(count)])

    def named_pin(self, names: Iterable[str]):
        for name in names:
            if name in self.pin_bag:
                self.pin_bag.remove(name)
                return name
        raise RuntimeError("Named pins %s not free" % ", ".join(names))


class ResourceBuilder(Protocol):
    def __call__(self, pins: PinManager, attrs: Attrs | None = None) -> list[Resource]: ...


def signature_resources(signature: Signature, default_name: str, number: int) -> ResourceBuilder:
    def make_resources(pins: PinManager, attrs: Attrs | None = None) -> list[Resource]:
        pinargs = {name: pins.p(Shape.cast(member.shape).width) for name, member in iterate_members(signature)}
        return [SignatureResource(number, signature=signature, default_name=default_name, attrs=attrs, **pinargs)]

    return make_resources


def append_resources(*args: ResourceBuilder):
    def make_resources(pins: PinManager, attrs: Attrs | None = None):
        return list(chain.from_iterable(map(lambda f: f(pins, attrs=attrs), args)))

    return make_resources
