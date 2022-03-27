# List of assumptions made during development

- RF has data forwarding from Tomasulo announcement bus
- read to `x0`/`RF0` return 0
- write to `x0`/`RF0` doesn't write
- separate RS for each FU
- writeback stage save data to RF and ROB (after getting output data from FU)
- commit stage update R-RAT
