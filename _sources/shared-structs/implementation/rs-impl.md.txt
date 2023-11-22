# Proposition of Reservation Station implementation

Here is an example proposition how to implement RS using transaction framework for internal communication. If you want
you can follow this proposition, if you don't, feel free to change anything you want.


## Internal data

### Actual Reservation Station

This is a buffer which has `R` rows. Each row has the following structure:

|v|opcode|`id_out`|`id_ROB`|`id_rs1`|`val_rs1`|`id_rs2`|`val_rs2`|
|-|------|--------|--------|--------|---------|--------|---------|

- `v` - "valid" - it is 1 if entry is a correct instruction which waits to be filled with operands/dispatched
- `id_rsX` - is 0 when the source value is ready (and is stored in the appropriate `val_rsX`) or not needed. It is
  non-zero when we wait for an operand to be ready.
- When the operand is ready we insert it to the appropriate `val_rsX` field and we put zero to `id_rsX`
- The instruction is ready to be dispatched if `v` is `1` and both `id_rs1`, `id_rs2` are `0`

### Used slots table

It is a table with `R` one-bit fields. Each field is `1` if this slot is used or is reserved to be used in the near
future (there is instruction in pipeline which will be saved to this slot).

When an entry in the RS is released, the corresponding entry in this table is switched from `1` to `0`.


## Internal methods

### Compare and substitute

Input:
- `tag` - identifier of field in RF which should be compared with `id_rsX` to check if there is need to store `value`
- `value` - value which should be stored in RS field if tag matches
- `position` - position in RS on which comparison and replacement should take place

Output:
- *null*

Side effects:
- When `tag` matches one of `id_rsX` saved in RS on `position` then `id_rsX` is cleared (set to 0) and `value` is saved
  in `val_rsX`

### Read row

Input:
- `position` - which RS row should be read

Output:
- `opcode` - instruction opcode for FU
- `val_rs1` - value of first operand
- `val_rs2` - value of second operand
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction

Side effects:
- *null*

### Clean row

Input:
- `position` - RS row which should be cleaned

Output:
- *null*

Side effects:
- `v` bit for entry on `position` set to `0`

### Get free slot

Input:
- *null*

Output:
- `position` - of the free slot in the RS

Side effects:
- *null*

### Mark slot as used

Input:
- `position` - of slot which should be marked as used

Output:
- *null*

Side effects:
- `position` slot in RS marked as used



## Proposition of implementation of external interfaces

### Get slot and mark as used

["Get free slot"](#get-free-slot) position and call ["Mark slot as used"](#mark-slot-as-used) with it.


### Compare and substitute all

Invokes ["Compare and substitute"](#compare-and-substitute) for each row of RS.


### Read and clean row

For given row `r` atomically ["Read row"](#read-row) and ["Clean row"](#clean-row)
