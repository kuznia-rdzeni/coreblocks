# Reservation Station

## Overview

The reservation station is used to store instructions which wait for their operands to be ready.
When the instruction is ready it should be woken up by wakeup logic and dispatched to the correct FU.


## Internal data

### Actual Reservation Station

This is a buffer which has `R` rows. Each row has the following structure:

|v|opcode|`id_out`|`id_ROB`|`id_rs1`|`val_rs1`|`id_rs2`|`val_rs2`|
|-|------|--------|--------|--------|---------|--------|---------|

Assumptions:
- `v` - "valid" - it is 1 if entry is a correct instruction which waits to be filled with operands/dispatched
- `id_rsX` - is 0 when the source value is ready (and is stored in the appropriate `id_valX`) or not needed. It is non-zero when
  we wait for an operand to be ready.
- When the operand is ready we insert it to the appropriate `val_rsX` field and we put zero to `id_rsX`
- The instruction is ready to be dispatched if `v` is `1` and both `id_rs1`, `id_rs2` are `0`

### Used slots table

It is a table with `R` one-bit fields. Each field is `1` if this slot is used or is reserved to be used in the near future
(there is instruction in pipeline which will be saved to this slot).

Assumptions:
- when an entry in the RS is released then their entry in this table is switched from `1` to `0`


## Interface

### Insert new instruction

Ready when:
- *implementation defined*

Input:
- `opcode` - instruction identifier for FU
- `id_rs1` - id of RF field where `src1` should be stored
- `id_rs2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `position` - position in the RS to which we should write this entry
- `start` - signal to start operation

Output:
- *null*

Side effects:
- Save data from input to the slot in RS specified by the `position` argument


### If free slot

Ready when:
- *always*

Input:
- *null*

Output:
- `free`
  - 0 -> no free slot
  - 1 -> there is a free slot

Side effects:
- *null*

### Get free slot

Ready when:
- there is a free slot in the RS

Input:
- *null*

Output:
- `position` - identifier of the free slot in the RS

Side effects:
- *null*


### Mark slot as used

Ready when:
- *implementation defined*

Input:
- `position` - id of slot which should be marked as used
- `start` - signal to start operation

Output:
- `err` - error code

Side effects:
- `position` slot in RS marked as used

Remarks:
- Function should check if position which we want to mark as used is free. If not, error should be returned (`err` =  1).


### Get slot and mark as used

Atomically make ["Get free slot"](#get-free-slot) and ["Mark slot as used"](#mark-slot-as-used).

Ready when:
- ["Mark slot as used"](#mark-slot-as-used) is ready and
- ["Get free slot"](#get-free-slot) is ready

Input:
- `start` - signal to start operation

Output:
- `position` - position returned by ["Get free slot"](#get-free-slot)
- `err` - error code returned by ["Mark slot as used"](#mark-slot-as-used)

Side effects:
- *null*

-----


### Compare and substitute

Ready when:
- *always*

Input:
- `tag` - identifier of RF which is announcement on Tomasulo bus
- `value` - value which is announcement on Tomasulo bus
- `position` - position in RF on which comparison and replacement should take place
- `start` - signal to start operation

Output:
- *null*

Side effects:
- When `tag` matches one of `id_rsX` saved in RS on `position` then `id_rsX` is cleared (set to 0) and `value` is saved
  in `val_rsX`


### Compare and substitute all

It invokes ["Compare and substitute"](#compare-and-substitute) for each row of RS.

Ready when:
- **always**

Input:
- `tag` - identifier of RF which is announcement on Tomasulo bus
- `value` - value which is announcement on Tomasulo bus
- `start` - signal to start operation

Output:
- *[optional]* err (0 - no error, 1 - error)

Side effects:
- Side effects of ["Compare and substitute"](#compare-and-substitute) for each row of RS

Remarks:
- *[optional]* if ["Compare and substitute"](#compare-and-substitute) for one of rows is not ready, then there can be
  returned error

----

### If instruction ready

Ready when:
- *always*

Input:
- `position` - instruction position in RS, which should be checked if it is ready to execute
- `start` - signal to start operation

Output:
- `inst_ready`:
  - 0 - instruction is still waiting for arguments
  - 1 - instruction is ready for execute

Side effects:
- *null*


### Read row

Ready when:
- *implementation defined*

Input:
- `position` - identifier of RS row, which should be read
- `start` - signal to start operation

Output:
- `opcode` - instruction identifier for FU
- `val_rs1` - value of first operand
- `val_rs2` - value of second operand
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `err` - error code

Side effects:
- *null*

Remarks:
- `err` is 1 if we try to read non valid RS row


### Clean row

Ready when:
- *implementation defined*

Input:
- `position` - identifier of RS row, which should be cleaned
- `start` - signal to start operation

Output:
- *null*

Side effects:
- `v` bit for entry on `position` set to `0`


### Read and clean row

Atomically make ["Read row"](#read-row) and ["Clean row"](#clean-row)

Ready when:
- ["Read row"](#read-row) is ready and
- ["Clean row"](#clean-row) is ready

Input:
- `position` - identifier of RS row, which should be read and cleared
- `start` - signal to start operation

Output:
- `opcode` - instruction identifier for FU
- `val_rs1` - value of first operand
- `val_rs2` - value of second operand
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `err` - error code

Side effects:
- `v` bit for entry on `position` set to `0`


## Reset / Initial state

In initial state:
- all `v` fields should have value `0`
- all fields in "Used slots table" should have value `0`


## Remarks

- I assume that the identifier of the RS row to be read and cleaned during dispatching to FU will be provided by the wakeup logic
