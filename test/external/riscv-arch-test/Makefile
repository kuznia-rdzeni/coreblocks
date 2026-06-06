MAKEFILE_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

ARCH_TEST_NOT_COMPILING =
ARCH_TEST_EXCLUDE_FAILING =
ARCH_TEST_EXCLUDE_TIMEOUT =

ARCH_TEST_NOT_COMPILING += Sm
ARCH_TEST_NOT_COMPILING += PMPSm

# sail does not have configuration for read-only FS/VS in mstatus - riscv/sail-riscv#1722
ARCH_TEST_EXCLUDE_FAILING += S
# hits assertion in rf
ARCH_TEST_EXCLUDE_FAILING += Zifencei
# assumes satp.PPN is writeable
ARCH_TEST_EXCLUDE_FAILING += Sv
# don't know
ARCH_TEST_EXCLUDE_FAILING += InterruptsS InterruptsU
# amo* causes load exceptions - kuznia-rdzeni/coreblocks#960
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZaamo
# sail does not support reservations sets > 12 bits
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZalrsc
# don't know
ARCH_TEST_EXCLUDE_FAILING += SsstrictSm

ARCH_TEST_EXCLUDE_TIMEOUT += U
ARCH_TEST_EXCLUDE_TIMEOUT += ExceptionsS
ARCH_TEST_EXCLUDE_TIMEOUT += PMPS PMPU PMPZca PMPZaamo PMPZalrsc
ARCH_TEST_EXCLUDE_TIMEOUT += SsstrictS SsstrictU

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
