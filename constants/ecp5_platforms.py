from collections.abc import Callable, Iterable
from itertools import chain
from typing import TypeAlias
from amaranth import *
from amaranth.build.dsl import Subsignal
from amaranth.vendor import LatticeECP5Platform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN
from amaranth.lib.wiring import Signature, Flow

from constants.ecp5_pinout import ecp5_bg756_pins, ecp5_bg756_pclk

from transactron.lib import AdapterBase

__all__ = ["make_ecp5_platform"]


def SignatureResource(*args, pins: "PinManager", signature: Signature, default_name: str, conn=None):  # noqa: N802
    io = []

    for hier_name, member in signature.members.flatten():
        if not member.is_port:
            continue
        name = "__".join(str(x) for x in hier_name)
        dir = "i" if member.flow == Flow.In else "o"
        io.append(Subsignal(name, Pins(pins.p(Shape.cast(member.shape).width), dir=dir, conn=conn)))

    return Resource.family(*args, default_name=default_name, ios=io)


def AdapterResource(*args, en, done, data_in, data_out, conn=None):  # noqa: N802
    io = []

    io.append(Subsignal("en", Pins(en, dir="i", conn=conn, assert_width=1)))
    io.append(Subsignal("done", Pins(done, dir="o", conn=conn, assert_width=1)))
    if data_in:
        io.append(Subsignal("data_in", Pins(data_in, dir="i", conn=conn)))
    if data_out:
        io.append(Subsignal("data_out", Pins(data_out, dir="o", conn=conn)))

    return Resource.family(*args, default_name="adapter", ios=io)


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


ResourceBuilder: TypeAlias = Callable[[PinManager], list[Resource]]


def signature_resources(signature: Signature, default_name: str):
    def make_resources(pins: PinManager) -> list[Resource]:
        return [SignatureResource(0, signature=signature, pins=pins, default_name=default_name)]

    return make_resources


def adapter_resources(adapter: AdapterBase, number: int):
    def make_resources(pins: PinManager) -> list[Resource]:
        return [
            AdapterResource(
                number,
                en=pins.p(),
                done=pins.p(),
                data_in=pins.p(adapter.data_in.shape().size),
                data_out=pins.p(adapter.data_out.shape().size),
            )
        ]

    return make_resources


def append_resources(*args: ResourceBuilder):
    def make_resources(pins: PinManager):
        return list(chain.from_iterable(map(lambda f: f(pins), args)))

    return make_resources


def make_ecp5_platform(resource_builder: ResourceBuilder):
    pins = PinManager(ecp5_bg756_pins)

    # Tutorial for synthesis in amaranth:
    # https://github.com/RobertBaruch/amaranth-tutorial/blob/main/9_synthesis.md
    class ECP5BG756Platform(LatticeECP5Platform):
        device = "LFE5UM5G-85F"
        package = "BG756"
        speed = "8"
        default_clk = "clk"
        default_rst = "rst"

        clk_pin = pins.named_pin(ecp5_bg756_pclk)
        resources = [
            Resource("rst", 0, PinsN(pins.p(), dir="i"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("clk", 0, Pins(clk_pin, dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        ] + resource_builder(pins)

        connectors = []

        def toolchain_program(self):
            pass

    return ECP5BG756Platform
