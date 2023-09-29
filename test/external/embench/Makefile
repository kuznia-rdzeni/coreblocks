all: build

copy-config:
	cp -v -r -f board_config/coreblocks-sim embench-iot/config/riscv32/boards

copy-coreblocks-benchmarks:
	cp -v -r -f coreblocks_benchmarks/* embench-iot/src

build: copy-config copy-coreblocks-benchmarks
	embench-iot/build_all.py \
		--builddir ../build \
		--logdir ../logs \
		--arch riscv32 \
		--chip generic \
		--board coreblocks-sim

clean:
	rm -rf build logs

.PHONY: all copy-config clean
