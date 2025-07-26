<div align="center">
    <img src="docs/images/logo.svg" width="250" />
</div>

# Coreblocks

Coreblocks is an experimental, modular out-of-order [RISC-V](https://riscv.org/specifications/) core generator implemented in [Amaranth](https://github.com/amaranth-lang/amaranth/). Its design goals are:

 * Simplicity. Coreblocks is an academic project, accessible to students.
   It should be suitable for teaching essentials of out-of-order architectures.
 * Modularity. We want to be able to easily experiment with the core by adding, replacing and modifying modules without changing the source too much.
   For this goal, we designed a transaction system called [Transactron](https://github.com/kuznia-rdzeni/transactron), which is inspired by [Bluespec](http://wiki.bluespec.com/).
 * Fine-grained testing. Outside of the integration tests for the full core, modules are tested individually.
   This is to support an agile style of development.

In the future, we would like to achieve the following goals:

 * Performance (up to a point, on FPGAs). We would like Coreblocks not to be too sluggish, without compromising the simplicity goal.
   We don't wish to compete with high performance cores like [BOOM](https://github.com/riscv-boom/riscv-boom) though.
 * Wide RISC-V support.
   The core can currently run [Zephyr](https://github.com/kuznia-rdzeni/zephyr-on-litex-coreblocks) and [a MMU-less Linux kernel](https://github.com/kuznia-rdzeni/linux-on-litex-coreblocks).
   Running a fully-featured Linux core in supervisor mode is our next target.

## Getting started:

First, ensure you have [PDM](https://pdm-project.org/) installed. Then run:
```
     $ pdm install
```


## State of the project

The core currently supports the full unprivileged RV32I instruction set and a number of extensions, including:

 * M - integer multiplication and division, with Zmmul only as an option,
 * A - atomic instructions, comprising of Zaamo and Zalrsc (without multi-core support),
 * C - compressed instructions,
 * B - bit manipulation, comprising of Zba, Zbb and Zbs, extension Zbc is implemented too.

Machine mode is fully implemented. Support for supervisor mode is currently missing.

Coreblocks can be easily integrated with [LiteX](https://github.com/enjoy-digital/litex) SoC generator.

## Documentation

The [documentation for our project](https://kuznia-rdzeni.github.io/coreblocks/) is automatically generated using [Sphinx](https://www.sphinx-doc.org/).

Resource usage and maximum clock frequency is [automatically measured and recorded](https://kuznia-rdzeni.github.io/coreblocks/dev/benchmark/).

## Contributing

Set up the [development environment](https://kuznia-rdzeni.github.io/coreblocks/Development_environment.html) following the project documentation.

External contributors are welcome to submit pull requests for simple contributions directly.
For larger changes, please discuss your plans with us through the [issues page](https://github.com/kuznia-rdzeni/coreblocks/issues) or the [discussions page](https://github.com/kuznia-rdzeni/coreblocks/discussions) first.
This way, you can ensure that the contribution fits the project and will be merged sooner.

## License

Copyright © 2022-2025, University of Wrocław.

This project is [three-clause BSD](https://github.com/kuznia-rdzeni/coreblocks/blob/master/LICENSE) licensed.
