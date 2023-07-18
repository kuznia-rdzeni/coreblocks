from abc import ABC, abstractmethod
from collections.abc import Iterable
from amaranth.build.dsl import Subsignal
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN

from constants.ecp5_pinout import ecp5_bg381_pins, ecp5_bg381_pclk

from coreblocks.peripherals.wishbone import WishboneParameters

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


class ResourceBuilder(ABC):
    def p(self, count: int = 1):
        return " ".join([self.pin_bag.pop() for _ in range(count)])

    def named_pin(self,names: list[str]):
        for name in names:
            if name in self.pin_bag:
                self.pin_bag.remove(name)
                return name

    def set_pins(self, pins: Iterable[str]):
        self.pin_bag = list(pins)

    @abstractmethod
    def resources(self) -> list[Resource]:
        raise NotImplementedError


class WishboneResourceBuilder(ResourceBuilder):
    def __init__(self, wb_params: WishboneParameters):
        self.wb_params = wb_params

    def resources(self) -> list[Resource]:
        return [
            WishboneResource(
                0,
                dat_r=self.p(self.wb_params.data_width),
                dat_w=self.p(self.wb_params.data_width),
                rst=self.p(),
                ack=self.p(),
                adr=self.p(self.wb_params.addr_width),
                cyc=self.p(),
                stall=self.p(),
                err=self.p(),
                lock=self.p(),
                rty=self.p(),
                sel=self.p(self.wb_params.data_width // self.wb_params.granularity),
                stb=self.p(),
                we=self.p(),
            ),
        ]



def make_ecp5_platform(builder: ResourceBuilder):
    builder.set_pins(ecp5_bg381_pins)

    # Tutorial for synthesis in amaranth:
    # https://github.com/RobertBaruch/amaranth-tutorial/blob/main/9_synthesis.md
    class ECP5BG381Platform(LatticeECP5Platform):
        device = "LFE5UM5G-85F"
        package = "BG381"
        speed = "8"
        default_clk = "clk"
        default_rst = "rst"

        resources = [
            Resource("rst", 0, PinsN(builder.p(), dir="i"), Attrs(IO_TYPE="LVCMOS33")),
            Resource("clk", 0, Pins(builder.named_pin(ecp5_bg381_pclk), dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        ] + builder.resources()

        connectors = []

        def toolchain_program(self):
            pass

    return ECP5BG381Platform
