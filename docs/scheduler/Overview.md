# Scheduler overview

## Description

Scheduler is middle part of out processor. It is located after frontend and before execution units and its main tasks
are:

- register allocation
- renaming
- ROB entry allocation
- dispatching instruction to RS


## Schema

![Scheduler schema](../materials/img-scheduler-plan.jpg)

## Structure

We decided to split scheduler into 5 phases:
- register allocation
- renaming
- ROB entry allocation
- choosing RS to which instruction should be dispatched
- inserting instruction to RS

Each of this phases can be potentially one clock cycle but they can be merged in future because of optimisations, but
during implementation each should be treated as separate hardware block to get flexibility in future.


## More detailed description of each block

TODO
