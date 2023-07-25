<div align="center">
    <img src="docs/images/logo.svg" width="250" />
</div>

# Coreblocks

Coreblocks is an experimental, modular out-of-order [RISC-V](https://riscv.org/specifications/) core generator implemented in [Amaranth](https://github.com/amaranth-lang/amaranth/). Its design goals are:

 * Simplicity. Coreblocks is an academic project, accessible to students.
   It should be suitable for teaching essentials of out-of-order architectures.
 * Modularity. We want to be able to easily experiment with the core by adding, replacing and modifying modules without changing the source too much.
   For this goal, we designed a [transaction system](https://kuznia-rdzeni.github.io/coreblocks/Transactions.html) inspired by [Bluespec](http://wiki.bluespec.com/).
 * Fine-grained testing. Outside of the integration tests for the full core, modules are tested individually.
   This is to support an agile style of development.

In the future, we would like to achieve the following goals:

 * Performace (up to a point, on FPGAs). We would like Coreblocks not to be too sluggish, without compromising the simplicity goal.
   We don't wish to compete with high performance cores like [BOOM](https://github.com/riscv-boom/riscv-boom) though.
 * Wide(r) RISC-V support. Currently, we are focusing on getting the support for the core RV32I ISA right, but the ambitious long term plan is to be able to run full operating systems (e.g. Linux) on the core.

## State of the project

The core currently supports the full RV32I instruction set and several extensions, including M (multiplication and division) and C (compressed instructions).
Interrupts and exceptions are currently not supported.
Coreblocks can be used with [LiteX](https://github.com/enjoy-digital/litex) (currently using a [patched version](https://github.com/kuznia-rdzeni/litex/tree/coreblocks)).

The transaction system we use as the foundation for the core is well-tested and usable.
We plan to make it available as a separate Python package.

## Documentation

The [documentation for our project](https://kuznia-rdzeni.github.io/coreblocks/) is automatically generated using [Sphinx](https://www.sphinx-doc.org/).

Resource usage and maximum clock frequency is [automatically measured and recorded](https://kuznia-rdzeni.github.io/coreblocks/dev/benchmark/).

## Contributing

Set up the [development environment](https://kuznia-rdzeni.github.io/coreblocks/Development_environment.html) following the project documetation.

External contributors are welcome to submit pull requests for simple contributions directly.
For larger changes, please discuss your plans with us through the [issues page](https://github.com/kuznia-rdzeni/coreblocks/issues) or the [discussions page](https://github.com/kuznia-rdzeni/coreblocks/discussions) first.
This way, you can ensure that the contribution fits the project and will be merged sooner.

## License

Copyright © 2022-2023, University of Wrocław.

This project is [three-clause BSD](https://github.com/kuznia-rdzeni/coreblocks/blob/master/LICENSE) licensed.
