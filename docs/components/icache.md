# Instruction Cache

## Assumptions
Instruction cache works with the following assumptions:
1. Requested addresses are always a multiple of 4 (in bytes). RISC-V specification requires that instruction addresses are 4-byte aligned. Extension C, however, adds 16-bit instructions and thus relaxes the requirement of the 4-byte address alignment. Nevertheless, this case should be handled by the fetch unit.
2. Requests are fully pipelined and handled in order. Therefore, `issue_req` method can be called independently of `accept_res` method. The `issue_req` will just block if there is no space in the pipeline for another request.
3. The latency of the request is at least one cycle. When a cache miss happens, the latency can be arbitrarily big.

## Address mapping example
For `addr_width=32`, `num_of_sets=128`, `block_size_bytes=32`.
```
 31          16 15 14 13 12 11 10 09 08 07 06 05 04 03 02 01 00
|--------------|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
+--------------------+--------------------------+--------------+
| Tag                | Index                    | Offset       |
```
