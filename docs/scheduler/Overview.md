# Scheduler overview

## Description

Scheduler is the middle part of out processor.
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

Each of this phases can potentially take one clock cycle, but they can be merged as a potential future optimization.
During implementation each should be treated as a separate hardware block for future flexibility.


## More detailed description of each block

TODO
