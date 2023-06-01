
ISA_TESTS_DIR := riscv-tests/isa
ENV_DIR := environment/custom

include riscv-tests/isa/rv32ui/Makefrag
include riscv-tests/isa/rv32um/Makefrag

RISCV_PREFIX ?= riscv64-unknown-elf-
RISCV_GCC ?= $(RISCV_PREFIX)gcc
RISCV_GCC_OPTS ?= -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles

define compile_template

test-$(1)-%: $${ISA_TESTS_DIR}/$(1)/%.S
	$${RISCV_GCC} $${RISCV_GCC_OPTS} $(2) -I$${ISA_TESTS_DIR}/macros/scalar -I$${ENV_DIR} -T$${ENV_DIR}/link.ld $$< -o $$@

endef

$(eval $(call compile_template,rv32ui,-mabi=ilp32 -march=rv32i_zifencei))
$(eval $(call compile_template,rv32um,-mabi=ilp32 -march=rv32im_zifencei))

all: $(addprefix test-rv32ui-,${rv32ui_sc_tests}) $(addprefix test-rv32um-,${rv32um_sc_tests})

clean:
	rm test-*

