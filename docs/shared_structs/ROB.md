# Reorder buffer

## Overview

Reorder buffer have to store incoming instructions in program order to allow us too precisely handle exceptions during
out of order execution and to commit machine state in correct order. It usually store: PC, id of logical output
register, id of physical output register, done bit and valid bit. It should allow to check if the oldest instructions
are marked as done, to have possibility to commit ready, the oldest, instructions to machine state.


## External methods

### Insert to free slot

Input:
- `PC` - program counter
- `id_out` - id of RF field where instruction output should be stored
- `log_out` - identifier of logical registry where instruction output should be committed

Output:
- `position` - position on which instruction was inserted

Side effects:
- Instruction data are saved on `position` in ROB


### Mark entry as done

Input:
- `position` - position in the ROB which should be marked as done

Output:
- *null*

Side effects:
- Mark `position` entry as `done`

### Check if entry can be committed

Input:
- *null*

Output:
- `if_commit`
  - 0 - oldest entry can not be committed
  - 1 oldest entry can be committed

Side effects:
- *null*

### Get oldest instruction data

Input:
- *null*

Output:
- PC - program counter
- `id_out` - identifier of RF which should store output results
- `log_out` - identifier of logical registry, which should be updated by this operation

Side effects:
- *null*

### Get oldest instruction index

Input:
- *null*

Output:
- `position` - identifier of the oldest instruction

Side effects:
- *null*

### Clean entry

Input:
- `position` - ROB entry index which should be cleaned

Output:
- *null*

Side effects:
- `valid` bit for `position` entry set to 0
- update internal state so that it correctly point to oldest instruction after `position` is cleared
