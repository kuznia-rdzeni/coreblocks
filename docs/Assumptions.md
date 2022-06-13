# List of assumptions made during development

- RF has data forwarding from the Tomasulo announcement bus
- read of `x0`/`RF0` returns 0
- write to `x0`/`RF0` is a noop
- separate RS for each FU
- the writeback stage saves data to the RF and the ROB (after getting output data from FUs)
- the commit stage updates the R-RAT
