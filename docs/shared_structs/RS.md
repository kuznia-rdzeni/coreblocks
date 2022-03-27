# Reservation Station

## Overview

Reservation station is used to store instruction which wait for their operands to be ready. When instruction is ready
it should be waked up, by wakeup logic and dispatched to correct FU.

## Interfaces

### Insert new instruction

Ready when:
- data can be saved to RS

Input:
- `opcode` - instruction identifier for FU
- `id_s1` - id of RF field where `src1` should be stored
- `id_s2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `position` - position in RS to which we should write this entry
- `start` - signal to start operation

Output:
- *null*

Site effects:
- Save data from input to slot in RS specified by `position` argument

Remarks:
- We have to precompute if there is free slot to set `ready` bit. Probably this computation can be also used to get id
  of free slot. In such case saving will have possibility to use this information to make it's calculation faster (no
  need to compute the same thing second time).


### Get free slot

Ready when:
- there is free slot in RS

Input:
- *null*

Output:
- `position` - identifier of free slot in RS

Site effects:
- *null*


### Mark slot as used

Ready when:
- new slot can be marked as used

Input:
- `position` - id of position of slot which should be marked as used
- `start` - signal to start operation

Output:
- `err` - error code

Site effects:
- `position` slot in RS marked as used

Remarks:
- Function should check if position which we want to mark as used is free. If not error should be returned (`err` =  1).
