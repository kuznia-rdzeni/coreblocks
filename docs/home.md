# Introduction

Coreblocks is an out-of-order processor which implements the RISC-V architecture.

The graph below is a high level schematic of the core's microarchitecture.

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
    R[<b>RETIREMENT</b><br>-check readiness of instruction from the end of ROB<br>-update RAT<br>-deallocate old register<br>-deallocate ROB]

    ROB((ROB))
    RF((RF))
    FREE_RF((FREE RF))
    RAT((RAT))

    R --> FREE_RF --> S
    S & R & B <--> ROB
    B --> RF --> S
    S <--> RAT <--> R
```
