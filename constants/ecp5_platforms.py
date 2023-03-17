from amaranth.build.dsl import Subsignal
from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN

from constants.ecp5_pinout import ecp5_bg381_pins, ecp5_bg381_pclk

__all__ = ["ECP5BG381Platform"]


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


pin_bag = ecp5_bg381_pins[:]


def p(count: int = 1):
    return " ".join([pin_bag.pop() for _ in range(count)])


def named_pin(names: list[str]):
    for name in names:
        if name in pin_bag:
            pin_bag.remove(name)
            return name


# Tutorial for synthesis in amaranth:
# https://github.com/RobertBaruch/amaranth-tutorial/blob/main/9_synthesis.md
class ECP5BG381Platform(LatticeECP5Platform):
    device = "LFE5UM5G-85F"
    package = "BG381"
    speed = "8"
    default_clk = "clk"
    default_rst = "rst"

    resources = [
        Resource("rst", 0, PinsN(p(), dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("clk", 0, Pins(named_pin(ecp5_bg381_pclk), dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        WishboneResource(
            0,
            dat_r=p(32),
            dat_w=p(32),
            rst=p(),
            ack=p(),
            adr=p(30),
            cyc=p(),
            stall=p(),
            err=p(),
            lock=p(),
            rty=p(),
            sel=p(4),
            stb=p(),
            we=p(),
        ),
    ]

    connectors = []

    def toolchain_program(self):
        pass
