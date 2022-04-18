# Reorder buffer

## Overview

Reorder buffer have to buffer incoming instructions in program order to allow us too precisely handle exceptions during
out of order execution and to commit machine state in correct order.


## External methods

### Insert to free slot

Ready when:
- *implementation defined*

Input:
- `start` - signal to start operation
- `PC` - program counter
- `id_out` - id of RF field where instruction output should be stored
- `log_out` - identifier of logical registry where instruction output should be committed

Output:
- `position` - position on which instruction was inserted

Side effects:
- Instruction data are saved on `position` in ROB


### Mark entry as done

Ready when:
- *implementation defined*

Input:
- `position` - position in the ROB which should be marked as done
- `start` - signal to start operation

Output:
- *null*

Side effects:
- Mark `position` entry as `done`

### Check if entry can be committed

Ready when:
- *implementation defined*

Input:
- `start` - signal to start operation

Output:
- `if_commit`
  - 0 - oldest entry can not be committed
  - 1 oldest entry can be committed

Side effects:
- *null*

### Get oldest instruction data

Ready when:
- *implementation defined*

Input:
- `start` - signal to start operation

Output:
- PC - program counter
- `id_out` - identifier of RF which should store output results
- `log_out` - identifier of logical registry, which should be updated by this operation

Side effects:
- *null*

### Get oldest instruction index

Ready when:
- *implementation defined*

Input:
- `start` - signal to start operation

Output:
- `position` - identifier of the oldest instruction

Side effects:
- *null*

### Clean entry

Ready when:
- *implementation defined*

Input:
- `start` - signal to start operation
- `position` - ROB entry index which should be cleaned

Output:
- *null*

Side effects:
- `valid` bit for `position` entry set to 0
- update internal state so that it correctly point to oldest instruction after `position` is cleared
