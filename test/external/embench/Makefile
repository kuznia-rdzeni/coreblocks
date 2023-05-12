all: build

copy-config:
	cp -v -r -f board_config/cocotb embench-iot/config/riscv32/boards

build:
	embench-iot/build_all.py \
		--builddir ../build \
		--logdir ../logs \
		--arch riscv32 \
		--chip generic \
		--board cocotb

clean:
	rm -rf build