from collections.abc import Callable, Iterable
from itertools import chain
from typing import TypeAlias
from amaranth.build.dsl import Subsignal
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN

from constants.ecp5_pinout import ecp5_bg756_pins, ecp5_bg756_pclk

from coreblocks.peripherals.wishbone import WishboneParameters
from transactron.lib import AdapterBase

__all__ = ["make_ecp5_platform"]


def WishboneResource(  # noqa: N802
    *args, dat_r, dat_w, rst, ack, adr, cyc, stall, err, lock, rty, sel, stb, we, conn=None
):
    io = []

    io.append(Subsignal("dat_r", Pins(dat_r, dir="i", conn=conn)))
    io.append(Subsignal("dat_w", Pins(dat_w, dir="o", conn=conn)))
    io.append(Subsignal("rst", Pins(rst, dir="o", conn=conn, assert_width=1)))
    io.append(Subsignal("ack", Pins(ack, dir="i", conn=conn, assert_width=1)))
    io.append(Subsignal("adr", Pins(adr, dir="o", conn=conn)))
    io.append(Subsignal("cyc", Pins(cyc, dir="o", conn=conn, assert_width=1)))
    io.append(Subsignal("stall", Pins(stall, dir="i", conn=conn, assert_width=1)))
    io.append(Subsignal("err", Pins(err, dir="i", conn=conn, assert_width=1)))
    io.append(Subsignal("lock", Pins(lock, dir="o", conn=conn, assert_width=1)))
    io.append(Subsignal("rty", Pins(rty, dir="i", conn=conn, assert_width=1)))
    io.append(Subsignal("sel", Pins(sel, dir="o", conn=conn)))
    io.append(Subsignal("stb", Pins(stb, dir="o", conn=conn, assert_width=1)))
    io.append(Subsignal("we", Pins(we, dir="o", conn=conn, assert_width=1)))

    return Resource.family(*args, default_name="wishbone", ios=io)


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

    def named_pin(self, names: list[str]):
        for name in names:
            if name in self.pin_bag:
                self.pin_bag.remove(name)
                return name


ResourceBuilder: TypeAlias = Callable[[PinManager], list[Resource]]


def wishbone_resources(wb_params: WishboneParameters):
    def make_resources(pins: PinManager) -> list[Resource]:
        return [
            WishboneResource(
                0,
                dat_r=pins.p(wb_params.data_width),
                dat_w=pins.p(wb_params.data_width),
                rst=pins.p(),
                ack=pins.p(),
                adr=pins.p(wb_params.addr_width),
                cyc=pins.p(),
                stall=pins.p(),
                err=pins.p(),
                lock=pins.p(),
                rty=pins.p(),
                sel=pins.p(wb_params.data_width // wb_params.granularity),
                stb=pins.p(),
                we=pins.p(),
            ),
        ]

    return make_resources


def adapter_resources(adapter: AdapterBase, number: int):
    def make_resources(pins: PinManager) -> list[Resource]:
        return [
            AdapterResource(
                number,
                en=pins.p(),
                done=pins.p(),
                data_in=pins.p(adapter.data_in.shape().width),
                data_out=pins.p(adapter.data_out.shape().width),
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
        if clk_pin is None:
            raise RuntimeError("No free clk pin found.")
        resources = [
            Resource("rst", 0, PinsN(pins.p(), dir="i"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("clk", 0, Pins(clk_pin, dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        ] + resource_builder(pins)

        connectors = []

        def toolchain_program(self):
            pass

    return ECP5BG756Platform
