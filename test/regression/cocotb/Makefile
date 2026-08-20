# Common makefile for cocotb tests

# defaults
SIM ?= verilator
TOPLEVEL_LANG ?= verilog
ifeq ($(TRACES),1)
	SIM_BUILD ?= build/$(SIM)-trace
else
	SIM_BUILD ?= build/$(SIM)
endif

# TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
TOPLEVEL = top

# Yosys/Amaranth borkedness workaround
ifeq ($(SIM),verilator)
	# Verilog uses MAJOR.<MINOR as 3 digits> versioning - we can safely compress the version to number
	VERILATOR_VERSION_NUM = $(shell verilator --version | head -n 1 | cut -d ' ' -f 2 | tr -d '.')

	COMPILE_ARGS += -Wno-CASEINCOMPLETE -Wno-CASEOVERLAP -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNSIGNED -Wno-CMPCONST -Wno-LITENDIAN -Wno-UNOPTFLAT
	COMPILE_ARGS += $(shell [ $(VERILATOR_VERSION_NUM) -ge 5040 ] && echo "-Wno-ALWNEVER")

	BUILD_ARGS += -j`nproc`

	ifeq ($(TRACES),1)
		EXTRA_ARGS += --trace --trace-fst --trace-structs
	endif
endif

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
