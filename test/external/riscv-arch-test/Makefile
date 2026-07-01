MAKEFILE_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

ARCH_TEST_NOT_COMPILING =
ARCH_TEST_EXCLUDE_FAILING =
ARCH_TEST_EXCLUDE_TIMEOUT =

# from upstream: Insufficient WARL configuration options.
ARCH_TEST_NOT_COMPILING += Sm

# hits assertion in rf
ARCH_TEST_EXCLUDE_FAILING += Zifencei
# don't know
ARCH_TEST_EXCLUDE_FAILING += InterruptsU
# amo* causes load exceptions - kuznia-rdzeni/coreblocks#960
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZaamo ExceptionsSvZaamo
# sail does not support reservations sets > 12 bits
ARCH_TEST_EXCLUDE_FAILING += ExceptionsZalrsc ExceptionsSvZalrsc

# some of those could be a trap loop - need to investigate further
ARCH_TEST_EXCLUDE_TIMEOUT += S U
ARCH_TEST_EXCLUDE_TIMEOUT += InterruptsS ExceptionsS
ARCH_TEST_EXCLUDE_TIMEOUT += PMPSm PMPS PMPU PMPZaamo PMPZalrsc PMPZca
ARCH_TEST_EXCLUDE_TIMEOUT += SsstrictSm SsstrictS SsstrictU
ARCH_TEST_EXCLUDE_TIMEOUT += Sv ExceptionsSv SvPMP Svade
ARCH_TEST_EXCLUDE_TIMEOUT += Sstvala ZicntrS

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
