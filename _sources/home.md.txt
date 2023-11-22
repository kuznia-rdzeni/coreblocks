# Introduction

CoreBlocks is going to be an out-of-order processor which will implement a RISC-V microarchitecture.
The project will focus on flexibility, which should allow to easily make experiments with different
component implementations.

## Documentation

Documentation located in the `docs/` directory collects description of the whole processor.
In `Overview` a high level overview of CoreBlocks can be found.

Html versions of these pages and API documentation generated from code are available at [kuznia-rdzeni.github.io/coreblocks/](https://kuznia-rdzeni.github.io/coreblocks/)


```{mermaid}
graph
    F[<b>FRONTEND</b><br>-get instruction<br>-decode]
    F -->|FIFO| S
    S[<b>SCHEDULER</b><br>-allocate register<br>-rename<br>-allocate ROB<br>-send to RS]
    S --RS--> E
    E[<b>EXEC</b><br>-listen to incoming operands<br>-select instruction to execute<br>-send to FU<br>-deallocate RS]
    E --FU--> B
    B[<b>BACKEND</b><br>-listen for results from FU<br>-announce results to RF and RS<br>-mark done in ROB]
    B --> R
    R[<b>RETIREMENT</b><br>-check rediness of instruction from the end of ROB<br>-update RAT<br>-deallocate old register<br>-deallocate ROB]

    ROB((ROB))
    RF((RF))
    FREE_RF((FREE RF))
    RAT((RAT))

    R --> FREE_RF --> S
    S & R & B <--> ROB
    B --> RF --> S
    S <--> RAT <--> R
```
