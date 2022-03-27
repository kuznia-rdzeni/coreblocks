# Reservation Station

## Overview

Reservation station is used to store instruction which wait for their operands to be ready. When instruction is ready
it should be waked up by wakeup logic and dispatched to correct FU.


## Internal data

### Actual Reservation Station

This is a buffer which hes `R` rows. Each row has structure:

|v|opcode|`id_out`|`id_ROB`|`id_rs1`|`val_rs1`|`id_rs2`|`val_rs2`|
|-|------|--------|--------|--------|---------|--------|---------|

Assumptions:
- `v` - "valid" - it is 1 if entry is a correct instruction which wait to be filled with operands/dispatched
- `id_rsX` - is 0 when source value is ready (and is stored in appropriate `id_valX`) or not needed. It is non-zero when
  we wait for operand to be ready.
- When operand is ready we insert it to appropriate `id_valX` field and we put zero to `id_rsX`
- Instruction is ready to be dispatched if `v` has `1` and both `id_rs1`, `id_rs2` have values 0

### Used slots table

It is a table with `R` one-bit fields. Each field is `1` if this slot is used or is reserved to be used in near future
(there is instruction in pipeline which will be saved to this slot).

Assumptions:
- when entry in RS is released then their entry in this table is switched from `1` to `0`


## Interface

### Insert new instruction

Ready when:
- *implementation defined*

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


### If free slot

Ready when:
- *always*

Input:
- *null*

Output:
- `free` 
  - 0 -> no free slot
  - 1 -> there is a free slot


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
- *implementation defined*

Input:
- `position` - id of slot which should be marked as used
- `start` - signal to start operation

Output:
- `err` - error code

Site effects:
- `position` slot in RS marked as used

Remarks:
- Function should check if position which we want to mark as used is free. If not error should be returned (`err` =  1).


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

Site effects:
- When `tag` matches one of `id_rsX` saved in RS on `position` then `id_rsX` is cleared (set to 0) and `value` is saved
  in `val_rsX`


### Compare and substitute all

It invokes for each row of RS ["Compare and substitute"](#compare-and-substitute).

Ready when:
- ["Compare and substitute"](#compare-and-substitute) for all rows from RS is ready
- It should be **always** ready to don't loose any data from Tomasulo bus

Input:
- `tag` - identifier of RF which is announcement on Tomasulo bus
- `value` - value which is announcement on Tomasulo bus
- `start` - signal to start operation

Output:
- *null*

Site effects:
- Site effects of ["Compare and substitute"](#compare-and-substitute) for each row of RS

----

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

Remarks:
- `err` is 1 if we try to read non valid RS row


### Clean row

Ready when:
- *implementation defined*

Input:
- `position` - identifier of RS row, which should be read
- `start` - signal to start operation

Output:
- *null*

Site effects:
- `v` bit for entry on `position` set to `0`


### Read and clean row

Atomically make ["Read row"](#read-row) and ["Clean row"](#clean-row)

Ready when:
- ["Read row"](#read-row) is ready and
- ["Clean row"](#clean-row) is ready

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

Site effects:
- `v` bit for entry on `position` set to `0`


## Reset / Initial state

In initial state:
- all `v` fields should have value `0`
- all fields in "Used slots table" should have value `0`


## Remarks

- I assume that identifier of RS row to be read and cleaned during dispatching to FU will be provided by wakeup logic
