# Register allocation

## Overview

This block allocate new physical register for instruction output. When `log_out` != 0 it take an free register file slot
from Free-RF list and allocate it for this instruction.

## External Interface Methods

*Null*

## Block side effects

This block should:
- Pop a new instruction from instruction input FIFO
- Pop a free-RF from Free-RF List if `log_out!=0` 
- Execute ["Insert new instruction"](../scheduler/Renaming.md#insert-new-instruction) from Renaming
