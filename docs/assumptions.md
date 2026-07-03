# List of assumptions made during development

- RF has data forwarding from the Tomasulo announcement bus
- read of `x0`/`RF0` returns 0
- write to `x0`/`RF0` is a noop
- the announcement stage saves data to the RF and the ROB (after getting output data from FUs)
- the retirement stage updates the R-RAT
