MAKEFILE_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

ARCH_TEST_NOT_COMPILING =
ARCH_TEST_EXCLUDE_FAILING =
ARCH_TEST_EXCLUDE_TIMEOUT =

ARCH_TEST_NOT_COMPILING += Sm
# riscv/riscv-arch-test#1658
ARCH_TEST_NOT_COMPILING += Sstvala

# sail does not have configuration for read-only FS/VS in mstatus - riscv/sail-riscv#1722
ARCH_TEST_EXCLUDE_FAILING += S
# hits assertion in rf
ARCH_TEST_EXCLUDE_FAILING += Zifencei
# assumes satp.PPN is writeable
ARCH_TEST_EXCLUDE_FAILING += Sv
# don't know
ARCH_TEST_EXCLUDE_FAILING += InterruptsU
# amo* causes load exceptions - kuznia-rdzeni/coreblocks#960
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZaamo
# sail does not support reservations sets > 12 bits
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZalrsc
# don't know - pmpsm_cfg_XWR_all-01.S
ARCH_TEST_EXCLUDE_FAILING += PMPSm
# don't know - pmpzca_misaligned_napot.S
ARCH_TEST_EXCLUDE_FAILING += PMPZca

# some of those could be a trap loop - need to investigate further
ARCH_TEST_EXCLUDE_TIMEOUT += U
ARCH_TEST_EXCLUDE_TIMEOUT += ZicntrS
ARCH_TEST_EXCLUDE_TIMEOUT += InterruptsS ExceptionsS
ARCH_TEST_EXCLUDE_TIMEOUT += PMPS PMPU PMPZaamo PMPZalrsc
ARCH_TEST_EXCLUDE_TIMEOUT += SsstrictSm SsstrictS SsstrictU

EXCLUDE_EXTENSIONS_SET = $(ARCH_TEST_NOT_COMPILING) $(ARCH_TEST_EXCLUDE_FAILING) $(ARCH_TEST_EXCLUDE_TIMEOUT)
EXCLUDE_EXTENSIONS = $(shell echo "$(EXCLUDE_EXTENSIONS_SET)" | tr ' ' ',')
CONFIG_FILES = $(MAKEFILE_DIR)/coreblocks/coreblocks-full/test_config.yaml

export EXCLUDE_EXTENSIONS
export CONFIG_FILES

all: tests

tests:
	$(MAKE) -C riscv-arch-test
	@rm -rf elfs
	@cp -r riscv-arch-test/work/coreblocks-full/elfs .

clean:
	$(MAKE) -C riscv-arch-test clean
	@rm -rf elfs

.PHONY: all tests clean
