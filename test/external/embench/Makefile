all: build

copy-config:
	cp -v -r -f board_config/coreblocks-sim embench-iot/config/riscv32/boards

copy-config-fast: copy-config
	cp -v -r -f board_config/coreblocks-sim embench-iot/config/riscv32/boards/coreblocks-sim-fast
	sed -i 's/^cpu_mhz = .*/cpu_mhz = 0.01/' embench-iot/config/riscv32/boards/coreblocks-sim-fast/board.cfg

build: copy-config
	embench-iot/build_all.py \
		--builddir ../build \
		--logdir ../logs \
		--arch riscv32 \
		--chip generic \
		--board coreblocks-sim

build-fast: copy-config-fast
	embench-iot/build_all.py \
		--builddir ../build-fast \
		--logdir ../logs-fast \
		--arch riscv32 \
		--chip generic \
		--board coreblocks-sim-fast

clean:
	rm -rf build logs build-fast logs-fast

.PHONY: all copy-config copy-config-fast build build-fast clean
