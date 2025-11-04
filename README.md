<div align="center">
    <img src="docs/images/logo.svg" width="250" />
</div>

# Coreblocks

Coreblocks is an experimental, modular out-of-order [RISC-V](https://riscv.org/specifications/) core generator implemented in [Amaranth](https://github.com/amaranth-lang/amaranth/). Its design goals are:

 * Simplicity. Coreblocks is an academic project, accessible to students.
   It should be suitable for teaching essentials of out-of-order architectures.
 * Modularity. We want to be able to easily experiment with the core by adding, replacing and modifying modules without changing the source too much.
   For this goal, we designed a transaction system called [Transactron](https://github.com/kuznia-rdzeni/transactron), which is inspired by [Bluespec](http://github.com/b-lang-org/bsc).
 * Fine-grained testing. Outside of the integration tests for the full core, modules are tested individually.
   This is to support an agile style of development.

In the future, we would like to achieve the following goals:

 * Performance (up to a point, on FPGAs). We would like Coreblocks not to be too sluggish, without compromising the simplicity goal.
   We don't wish to compete with high performance cores like [BOOM](https://github.com/riscv-boom/riscv-boom) though.
 * Wide RISC-V support.
   The core can currently run [Zephyr](https://github.com/kuznia-rdzeni/zephyr-on-litex-coreblocks) and [a MMU-less Linux kernel](https://github.com/kuznia-rdzeni/linux-on-litex-coreblocks).
   Running a fully-featured Linux core in supervisor mode is our next target.

## State of the project

The core currently supports the full unprivileged RV32I instruction set and a number of extensions, including:

 * M - integer multiplication and division, with Zmmul only as an option,
 * A - atomic instructions, comprising of Zaamo and Zalrsc (without multi-core support),
 * C - compressed instructions,
 * B - bit manipulation, comprising of Zba, Zbb and Zbs, extension Zbc is implemented too.

Machine and user modes are fully implemented. Support for supervisor mode is currently missing.

Coreblocks can be easily integrated with [LiteX](https://github.com/enjoy-digital/litex) SoC generator.

## Community

We have an community IRC channel - [#coreforge at libera.chat](https://web.libera.chat/#coreforge).
You are welcome to join and ask questions, discuss development, or share feedback about [Coreforge projects](https://github.com/kuznia-rdzeni) :)

Coreblocks is maintained under the [Coreforge Foundation](https://kuznia-rdzeni.org)
and is **looking for new contributors!** - Want to get involved? We will be happy to help you.

## Documentation

The [documentation for our project](https://kuznia-rdzeni.github.io/coreblocks/) is automatically generated using [Sphinx](https://www.sphinx-doc.org/).
*It is currently a bit outdated.*

Resource usage and maximum clock frequency is [automatically measured and recorded](https://kuznia-rdzeni.github.io/coreblocks/dev/benchmark/).

## Contributing

Set up the [development environment](https://kuznia-rdzeni.github.io/coreblocks/Development_environment.html) following the project documentation.

For larger changes, please discuss your plans with us first, so you can ensure that the contribution fits the project and will be merged sooner.
You are welcome to submit pull requests for simple contributions directly.

## License

Copyright © 2022-2025, University of Wrocław.

This project is [three-clause BSD](https://github.com/kuznia-rdzeni/coreblocks/blob/master/LICENSE) licensed.
