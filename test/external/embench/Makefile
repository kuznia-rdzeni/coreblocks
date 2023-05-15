all: build

copy-config:
	cp -v -r -f board_config/coreblocks-sim embench-iot/config/riscv32/boards

build: copy-config
	embench-iot/build_all.py \
		--builddir ../build \
		--logdir ../logs \
		--arch riscv32 \
		--chip generic \
		--board coreblocks-sim

clean:
	rm -rf build logs

.PHONY: all copy-config clean
