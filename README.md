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

## Contributing

Set up the [development environment](https://kuznia-rdzeni.github.io/coreblocks/Development_environment.html) following the project documetation.
