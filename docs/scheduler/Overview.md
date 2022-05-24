# Scheduler overview

## Description

The scheduler is the middle part of our processor.
It is located after the frontend and before execution units.
Its main tasks are:

- register allocation
- renaming
- ROB entry allocation
- dispatching instructions to RSs


## Schema

![Scheduler schema](../materials/img-scheduler-plan.jpg)

## Structure

We decided to split the scheduler into 5 phases:
- register allocation
- renaming
- ROB entry allocation
- choosing the RS to which instruction should be dispatched
- inserting instruction to RS

Each phase can potentially take one clock cycle, but they can be merged as a potential future optimization.
During implementation each phase should be treated as a separate hardware block for future flexibility.


## More detailed description of each block

TODO
