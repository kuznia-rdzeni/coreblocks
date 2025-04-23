
ISA_TESTS_DIR := riscv-tests/isa
ENV_DIR := environment/custom

include riscv-tests/isa/rv32ui/Makefrag
include riscv-tests/isa/rv32um/Makefrag
include riscv-tests/isa/rv32ua/Makefrag
include riscv-tests/isa/rv32uc/Makefrag
include riscv-tests/isa/rv32uzba/Makefrag
include riscv-tests/isa/rv32uzbb/Makefrag
include riscv-tests/isa/rv32uzbc/Makefrag
include riscv-tests/isa/rv32uzbs/Makefrag

RISCV_PREFIX ?= riscv64-unknown-elf-
RISCV_GCC ?= $(RISCV_PREFIX)gcc
RISCV_GCC_OPTS ?= -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles

define compile_template

test-$(1)-%: $${ISA_TESTS_DIR}/$(1)/%.S
	$${RISCV_GCC} $${RISCV_GCC_OPTS} $(2) -I$${ISA_TESTS_DIR}/macros/scalar -I$${ENV_DIR} -T$${ENV_DIR}/link.ld $$< -o $$@

endef

$(eval $(call compile_template,rv32ui,-mabi=ilp32 -march=rv32i_zifencei))
$(eval $(call compile_template,rv32um,-mabi=ilp32 -march=rv32im_zifencei))
$(eval $(call compile_template,rv32ua,-mabi=ilp32 -march=rv32ia_zifencei))
$(eval $(call compile_template,rv32uc,-mabi=ilp32 -march=rv32ic_zifencei))
$(eval $(call compile_template,rv32uzba,-mabi=ilp32 -march=rv32i_zba_zifencei))
$(eval $(call compile_template,rv32uzbb,-mabi=ilp32 -march=rv32i_zbb_zifencei))
$(eval $(call compile_template,rv32uzbc,-mabi=ilp32 -march=rv32i_zbc_zifencei))
$(eval $(call compile_template,rv32uzbs,-mabi=ilp32 -march=rv32i_zbs_zifencei))

all: $(addprefix test-rv32ui-,${rv32ui_sc_tests}) $(addprefix test-rv32um-,${rv32um_sc_tests}) $(addprefix test-rv32ua-,${rv32ua_sc_tests}) $(addprefix test-rv32uc-,${rv32uc_sc_tests}) $(addprefix test-rv32uzba-,${rv32uzba_sc_tests}) $(addprefix test-rv32uzbb-,${rv32uzbb_sc_tests}) $(addprefix test-rv32uzbc-,${rv32uzbc_sc_tests}) $(addprefix test-rv32uzbs-,${rv32uzbs_sc_tests})

clean:
	rm test-*
