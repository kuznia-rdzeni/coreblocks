
ISA_TESTS_DIR := riscv-tests/isa
ENV_DIR := environment/custom

include riscv-tests/isa/rv32ui/Makefrag

RISCV_PREFIX ?= riscv64-unknown-elf-
RISCV_GCC ?= $(RISCV_PREFIX)gcc
RISCV_GCC_OPTS ?= -mabi=ilp32 -march=rv32i -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles

test-%: ${ISA_TESTS_DIR}/rv32ui/%.S
	${RISCV_GCC} ${RISCV_GCC_OPTS} -I${ISA_TESTS_DIR}/macros/scalar -I${ENV_DIR} -T${ENV_DIR}/link.ld $< -o $@

all: $(addprefix test-,${rv32ui_sc_tests})

clean:
	rm test-*

