# Instruction Cache

## Interface
The instruction cache should expose three methods:
1. `issue_req`: This method issues an instruction lookup request.
2. `accept_resp`: This method returns the result of the lookup request.
3. `flush`: This method flushes the entire cache.

## Assumptions
The instruction cache operates under the following assumptions:
1. Requested addresses are always multiples of 4 bytes. The RISC-V specification requires instruction addresses to be 4-byte aligned, but the C extension introduces 16-bit instructions that relax this requirement. The fetch unit should handle this case.
2. Requests are fully pipelined and processed in order. As a result, the `issue_req` method can be invoked independently of the `accept_res` method. If there is no space in the pipeline for another request, `issue_req` will simply block.
3. The request latency is at least one cycle. If a cache miss occurs, the latency can be arbitrarily long.
4. Flushing the cache ensures that any requests issued after the flush will be refetched. However, there is no such guarantee for requests that have already been issued but are still waiting to be accepted.
5. Information regarding fetch errors is not cached. This means that if an error occurs during line refill, the subsequent access to that line will trigger another refill, which will most likely result in another error.

## Address mapping example
For `addr_width=32`, `num_of_sets=128`, `block_size_bytes=32`.
```
 31          16 15 14 13 12 11 10 09 08 07 06 05 04 03 02 01 00
|--------------|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
+--------------------+--------------------------+--------------+
| Tag                | Index                    | Offset       |
```
