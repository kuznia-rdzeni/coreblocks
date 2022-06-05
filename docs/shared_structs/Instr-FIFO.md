# Instruction FIFO

## Overview

This FIFO should be used as an buffer and store instruction between frontend and scheduler.

## Methods

### Get new instruction

Input:
- *null*

Output:
- `opcode_maj` - major instruction identifier
- `opcode_min` - minor instruction identifier for FU
- `log_rs1` - id of logical register with first input argument
- `log_rs2` - id of logical register with second input argument
- `log_out` - id of logical register for output result
- `imm` - immediate
- `PC` - program counter

Side effects:
- Pop oldest instruction from FIFO


### Put new instruction

Input:
- `opcode_maj` - major instruction identifier
- `opcode_min` - minor instruction identifier for FU
- `log_rs1` - id of logical register with first input argument
- `log_rs2` - id of logical register with second input argument
- `log_out` - id of logical register for output result
- `imm` - immediate
- `PC` - program counter

Output:
- *null*

Side effects:
- Push new instruction to FIFO
