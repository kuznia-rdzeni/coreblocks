from amaranth.vendor.lattice_ecp5 import LatticeECP5Platform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN

from constants.ecp5_pinout import ecp5_bg381_pins

__all__ = ["ECP5BG381Platform"]


# Tutorial for synthesis in amaranth:
# https://github.com/RobertBaruch/amaranth-tutorial/blob/main/9_synthesis.md
class ECP5BG381Platform(LatticeECP5Platform):
    device = "LFE5UM5G-85F"
    package = "BG381"
    speed = "8"
    default_clk = "clk"
    default_rst = "rst"

    resources = [
        Resource("rst", 0, PinsN(ecp5_bg381_pins[0], dir="i"), Attrs(IO_TYPE="LVCMOS33")),
        Resource("clk", 0, Pins(ecp5_bg381_pins[1], dir="i"), Clock(12e6), Attrs(IO_TYPE="LVCMOS33")),
        Resource("data_in", 0, Pins(" ".join(ecp5_bg381_pins[2:8]), dir="i")),
        Resource(
            "data_out",
            0,
            Pins(
                " ".join(ecp5_bg381_pins[9:56]),
                dir="o",
            ),
        ),
    ]

    connectors = []

    def toolchain_program(self):
        pass
