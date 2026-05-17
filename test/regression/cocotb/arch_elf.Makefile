# Makefile

# defaults
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
TOPLEVEL = top

# MODULE is the basename of the Python test file
MODULE = arch_elf_entrypoint

SIM_BUILD = build/arch_elf

# Yosys/Amaranth borkedness workaround
ifeq ($(SIM),verilator)
  EXTRA_ARGS += -Wno-CASEINCOMPLETE -Wno-CASEOVERLAP -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNSIGNED -Wno-CMPCONST -Wno-LITENDIAN -Wno-ALWNEVER -Wno-UNOPTFLAT
  BUILD_ARGS += -j`nproc`
endif

ifeq ($(TRACES),1)
  EXTRA_ARGS += --trace-fst --trace-structs
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
