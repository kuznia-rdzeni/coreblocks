# Reservation Station

## Overview

The reservation station is used to store instructions which wait for their operands to be ready.  When the instruction
is ready it should be woken up by wakeup logic and dispatched to the correct FU.

### Reset / Initial state

In initial state all rows are marked as invalid.


## External interface methods

### Get slot and mark as used

Input:
- *null*

Output:
- `position` - of a free slot in RS

Side effects:
- Slot on `position` marked as used


### Insert new instruction

Input:
- `opcode` - instruction opcode for FU
- `id_rs1` - id of RF field where `src1` should be stored
- `id_rs2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `position` - in the RS to which we should write this entry

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
- `position` - of RS row which should be read and cleared

Output:
- `opcode` - instruction opcode for FU
- `val_rs1` - value of first operand
- `val_rs2` - value of second operand
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction

Side effects:
- RS row on `position` marked as invalid

----

### Compare and substitute all

Input:
- `tag` - from RF for which RS should be checked for
- `value` - value which should be written to fields of RS with matching tag

Output:
- *null*

Side effects:
- For each row of RS if in this row are fields tagged with `tag` store
  `value` in these fields.


## External interface signals

- `free`: one-bit signal indicating if there is a free slot in the RS
