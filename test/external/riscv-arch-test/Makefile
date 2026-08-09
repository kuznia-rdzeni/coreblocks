MAKEFILE_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

CONFIG_FILES = $(MAKEFILE_DIR)/coreblocks/coreblocks-full/test_config.yaml
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
