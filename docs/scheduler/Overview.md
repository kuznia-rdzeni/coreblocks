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

```{mermaid}
graph
    Reg;
    Reg[<b>REGISTER ALLOCATION</b><br>-get free register from FREE RF list]
    Reg --> Rename;
    Rename[<b>RENAMING</b><br>-rename source registers using F-RAT<br>-save mapping to allocated output register in F-RAT]
    Rename --> AlocRob;
    AlocRob[<b>ROB ALLOCATION</b><br>-get ID of free entry in ROB<br>-save instruction in ROB entry]
    AlocRob --> Select;
    Select[<b>RS SELECTION</b><br>-choose RS to which instruction should be send<br>-reserve entry in that RS]
    Select --> Insert;
    Insert[<b>RS INSERTION</b><br>-insert instruction to selected RS<br>-get operands from RF<br>-save them in RS field of new instruction]
```

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
