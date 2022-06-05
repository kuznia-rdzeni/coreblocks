# RS selection

## Overview

This block is responsible for selection an RS to which instruction should be routed,
possibly taking into account some metadata, for example speed of FU connected to that RS
or how big is load of given RS. After selection of the RS it should reserve in that RS
an entry. Additionally it has to inform proper wakeup and select logic block,
that new instruction will be inserted to reserved entry in RS.

## Example internal data

In the simplest case we can select RS using instruction opcode routing. As described in chapter 24 of RiscV unprivileged
architecture there is possible to split instruction into parts based on bits [6:2]. So we can use such splitting.

Let `R_tab` will be routing table with 32 entries. Each entry is indexed by bits [6:2] from the instruction and in the
entry there is stored identifier of FU (or set of FU-s) to which this instruction should be route (if this will be
needed there is possibility to add hierarchical routing). `R_tab` will be ROM generated before amaranth elaboration.

![Source: RiscV unprivileged architecture](../materials/img-RS_selection-proposition.png)

## Methods

### Route new instruction

Choose FU to which instruction should be send (e.g. based on `opcode_maj` and `R_tab`) reserve position in RS for these
FU and insert this instruction to RS and wakeup logic.

Input:
- `opcode_maj` - major instruction identifier
- `opcode_min` - minor instruction identifier for FU
- `id_rs1` - id of RF field where `src1` should be stored
- `id_rs2` - id of RF field where `src2` should be stored
- `id_out` - id of RF field where instruction output should be stored
- `id_ROB` - id of ROB entry which is allocated for this instruction
- `imm` - immediate

Output:
- *null*

Side effects:
- If instruction cannot be routed (e.g. it has wrong opcodes) report it
- In chosen RS there is reserved an entry for this instruction
- Proper wakeup and select logic is informed about this new instruction
