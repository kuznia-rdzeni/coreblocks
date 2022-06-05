# Proposition of reorder buffer implementation

## Internal data


ROB entry consist of:

- PC - program counter
- `id_out` - identifier of RF which should store output results
- `log_out` - identifier of logical registry, which should be updated by this operation
- valid - bit equal to 1 if this entry is valid
- done - bit equal to 1 if this operation has already ended work

### Proposition 1

ROB is a memory with 2 associated pointers. `p_sta` point to first used slot (newest instruction), `p_end` point to last
used slot (oldest non committed instruction). We assume that when `p_sta`+1=`p_end` then ROB is full.

### Proposition 2

ROB is a memory with associated list of free ROB entries. If this list is empty we assume, that ROB is full.



## Internal methods propositions

### Get free entry

Input:
- *null*

Output:
- `id_ROB` - id of free ROB entry

Side effects:
- *null*


### Insert instruction to entry

Input:
- `PC` - program counter
- `id_out` - id of RF field where instruction output should be stored
- `log_out` - identifier of logical registry where instruction output should be committed
- `position` - position in the ROB to which we should write this entry

Output:
- *null*

Side effects:
- Save data from input to the slot in ROB specified by the `position` argument
- Mark `position` entry as `valid`
- Mark `position` entry as not `done`



### Insert to free slot

Methods in transaction:
- ["Get free entry"](#get-free-entry)
- ["Insert instruction to entry"](#insert-instruction-to-entry)

Input:
- `PC` - program counter
- `id_out` - id of RF field where instruction output should be stored
- `log_out` - identifier of logical registry where instruction output should be committed

Output:
- `position` - position returned by ["Get free slot"](#get-free-slot)

Side effects:
- The same as for ["Insert instruction to entry"](#insert-instruction-to-entry)
