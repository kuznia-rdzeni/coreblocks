# Makefile for arch regression cocotb tests

# defaults
SIM ?= verilator
TOPLEVEL_LANG ?= verilog
SIM_BUILD ?= build/riscv-arch-test/$(SIM)

# TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
TOPLEVEL = top

# MODULE is the basename of the Python test file
MODULE = arch_elf_entrypoint

# Yosys/Amaranth borkedness workaround
ifeq ($(SIM),verilator)
  EXTRA_ARGS += -Wno-CASEINCOMPLETE -Wno-CASEOVERLAP -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNSIGNED -Wno-CMPCONST -Wno-LITENDIAN -Wno-UNOPTFLAT -Wno-ALWNEVER
  BUILD_ARGS += -j`nproc`
endif

ifeq ($(TRACES),1)
  EXTRA_ARGS += --trace-fst --trace-structs
endif

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
