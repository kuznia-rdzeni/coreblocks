
import cocotb
from cocotbext.wishbone.monitor import WishboneSlave

@cocotb.test()
async def test(dut):
    wb_instr = WishboneSlave(dut, "wb_instr", dut.clk,
            width=32,
            bus_separator="__",
            signals_dict={
                "cyc": "cyc",
                "stb": "stb",
                "we": "we",
                "datwr": "dat_w",
                "datrd": "dat_r",
                "ack": "ack",
                "err": "err",
                "rty": "rty"
            })

    wb_data = WishboneSlave(dut, "wb_data", dut.clk,
            width=32,
            bus_separator="__",
            signals_dict={
                "cyc": "cyc",
                "stb": "stb",
                "we": "we",
                "datwr": "dat_w",
                "datrd": "dat_r",
                "ack": "ack",
                "err": "err",
                "rty": "rty"
            })
