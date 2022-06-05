# Renaming

## Overview

This block is responsible for making register renaming. For each logical register from input instruction, this block
should turn it into physical register from register file. To do it, this block should use F-RAT which represent actual
state of mapping between logical and physical registers.

Additionally this block should update mapping of logical output register so that F-RAT will point to physical output
register which was allocated in previous step.


## External Interface Methods

### Insert new instruction

Input:
- `opcode_maj` - major instruction identifier
- `opcode_min` - minor instruction identifier for FU
- `id_out` - id of RF field where instruction output should be stored
- `log_rs1` - id of logical register with first input argument
- `log_rs2` - id of logical register with second input argument
- `log_out` - id of logical register for output result
- `imm` - immediate
- `PC` - program counter

Output:
- *null*

Side effects:
- `F-RAT[log_out]=id_out`
