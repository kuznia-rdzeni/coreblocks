# Makefile

# defaults
SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../core.v
# use VHDL_SOURCES for VHDL files

# TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
TOPLEVEL = top

# MODULE is the basename of the Python test file
MODULE = test

# avoid error due to Verilator's warnings
EXTRA_ARGS = -Wno-fatal

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/simulators/Makefile.verilator

