# ROB allocation

## Overview

This block is responsible for allocation of a free entry in ROB for a new instruction.
First it should find an empty entry in ROB, then mark it as used and fill it with
instruction data and metadata. Especially it should set `done` bit in ROB on 0, to mark
that this instruction hasn't finished yet.


## External Interface Methods

### Insert new instruction

Input:
- `opcode_maj` - major instruction identifier
- `opcode_min` - minor instruction identifier for FU
- `id_rs1` - id of RF field where `src1` should be stored
- `id_rs2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `log_out` - logical identifier of output registry
- `imm` - immediate
- `PC` - program counter

Output:
- *null*

Side effects:
- Allocate an entry in ROB:
  - Find a free slot in ROB
  - Mark this slot as used
  - Fill this slot with needed data
