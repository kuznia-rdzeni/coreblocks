# Reservation Station

## Overview

The reservation station is used to store instructions which wait for their operands to be ready.  When the instruction
is ready it should be woken up by wakeup logic and dispatched to the correct FU.


## External interface methods

### Get slot and mark as used

Input:
- *null*

Output:
- `position` - position of a free slot in RS

Side effects:
- Slot on `position` marked as used


### Insert new instruction

Input:
- `opcode` - instruction identifier for FU
- `id_rs1` - id of RF field where `src1` should be stored
- `id_rs2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `position` - position in the RS to which we should write this entry

Output:
- *null*

Side effects:
- Save data from input to the slot in RS specified by the `position` argument

----

### Get ready vector

Input:
- *null*

Output:
- `inst_ready` - bit vector as long as RS, where bit on `position` mean:
  - 0 - instruction is still waiting for arguments
  - 1 - instruction is ready for execute

Side effects:
- *null*

### Read and clean row

Input:
- `position` - identifier of RS row, which should be read and cleared

Output:
- `opcode` - instruction identifier for FU
- `val_rs1` - value of first operand
- `val_rs2` - value of second operand
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction

Side effects:
- `v` bit for entry on `position` set to `0`

----

### Compare and substitute all

Input:
- `tag` - identifier of RF which is announcement on Tomasulo bus
- `value` - value which is announcement on Tomasulo bus

Output:
- *null*

Side effects:
- Substituting `tag` with `value` for each row of RS


## External interface signals

### If free slot

Output:
- `free`
  - 0 -> no free slot
  - 1 -> there is a free slot



## Reset / Initial state

In initial state:
- all `v` fields should have value `0`
- all fields in "Used slots table" should have value `0`
