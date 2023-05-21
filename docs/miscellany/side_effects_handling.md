# Handling side effects in FUs
Notes from 2023-05-19 meeting

## LSU variant

Currently, LSU handles only STORE side effects.
It does it by passing instructions to the next stage instantly and waiting until it reaches the retirement stage.
When LSU receives a notification about its current store instruction being retired, it executes the store into memory.
This way retirement of the executed store is guaranteed.

But memory LOADS also cause side effects. We would need to make the same thing with LOADS on the devices memory region (no, FENCE doesn't fix that).
The problem is that loads produce register result that needs to be announced and it is normally done by the backend stage.
However, with this arrangement, we get results in the retirement stage.
The proposed solution was to disable the backend announcement on that instruction and connect LSU with some Method directly to the announcement bus to announce the result.

## CSR variant

CSR Unit was designed to support LOAD and STORE CSR operation inside FU and normally pass completed instructions to the next pipeline stage.
It does it by delaying the execution of the instruction until it is the only instruction left in ROB.
This way, no other instruction could raise an exception or trigger an interrupt after the CSR instruction is executed.

Currently, the only problem is with interrupt handling. FU must trace when its instruction reaches the commit stage and delay all interrupts when they may happen on that instruction (until committed).

NOTE: If FU handles multiple instructions it must select its earliest instruction to check for first at suffix!

## Sub-conclusion

These are two ways to achieve the same thing - checking that suffix of ROB is empty (no smaller instructions in PC-order).

LSU uses retirement block to detect that, and does all other operations manually afterwards.

CSR Unit uses a special signal and holds instruction execution until suffix of ROB is empty (in reality it checks if the whole ROB is empty, but for a different reason).
After it, it passes the completed instruction to the next pipeline stage and it completes normally.

We agreed to accept the second way because it uses pipelining concepts.

## The ultimate fix

It turns out that adding separate flags for Interrupts and Exceptions in ROB solves the main issue of CSR variant (need of FU->Retirement instruction tracking, to disable triggering interrupts on that instruction, by delaying interrupts externally).

We can specify that if retirement sees Exception flag, it discards the current instruction and triggers the interrupt because instruction that caused an exception
shouldn't be committed.

If an instruction has Interrupt flag set, it should commit that instruction and trigger interrupt as it happened on the next instruction. At the retirement stage we already
must know the next pc address (if jump, it is already resolved, in other cases pc+4).

With that assumption, if some instruction is last in the ROB, interrupts cannot discard it (because interrupt flag would commit that instruction, and trigger interrupt after it)
and side effects would be preserved.

And two flags at once just work(TM). If instruction raises Exception, we can assume that it didn't cause any side effects.
We handle the Exception and treat interrupt like it happened during the execution of some exception handler.

NOTE: Specific edge case to CSR - What if CSR instructions disable/change interrupts and async interrupt is marked at that instruction (before execution)? It can be
fixed by inserting a filter between retirement and int_coordinator so that interrupt would be ignored. Interrupt would still have a pending flag enabled and will trigger
next time when valid (reenable is handled by the interrupt controller in a standard way).

All of that note applies only to the method of handling interrupts that clears the core. None of these issues appear in the lazy interrupt handling method, which disconnects FUs from actions that produce side effects.
