# Summary of papers about interrupts

## Introduction

This summary is a result of journal articles analysis which I made as a preparation to implement support for interrupts,
exceptions and speculation to core blocks. It looks like the choose of primary interrupts related structure determine
interrupt handling procedure. We have chosen a ROB, so there is a one "classical" implementation of ROB interrupt
handling procedure.  This procedure is used as a baseline for the improvements, but most of papers is pretty old
(1993-2001). Currently there is no much research ongoing on CPU interrupt handling and it is considered that this
problem is solved. Instead of that there are some works, which try to implement precise interrupts on GPU, but due to
differences in CPU and GPU characteristics this research can not be applied in an easy way to our project.

When I have prepared this overview I have decided to look through articles from different times to check on what people
were working in that time. So there is probably a lot of other works which can be worth to check. Specially:
- W. Walker and H. G. Cragon. “Interrupt processing in concurrent processors.” IEEE Computer, vol. 28, no. 6, June 1995
- M. Moudgill and S. Vassiliadis. “Precise interrupts.” IEEE Micro, vol. 16, no. 1, pp. 58–67, February 1996
this two works present a survey of the interrupt topic as for time of writing.

## Interrupt handling in old PC

- CDC6600 - interrupt handling is done by inserting a jump instruction to interrupt handler
- IBM360 - stop fetching and wait for all fetched instructions to be committed, next jump to interrupt handler
- CRAY-1 - similar to IBM360, but here latency can be even bigger due to vector instructions

## Interrupt Handling for Out-of-Order Execution Processors

> Interrupt Handling for Out, 1993
> H. C. Torng and Martin Day

This article describe one of first probes for implementation of exceptions in out-of-order processors. In that time ROB
was a very new idea. Authors of this paper introduced Instruction Window (IW) as theirs proposition for implementation
of interrupts in out-of-order processors. IW will store all dispatched instructions, which don't completed in case of
interrupt IW will be a part of context and will be copied to memory by interrupt handler. After restoring the context
all instructions from IW will be restarted so that the state of CPU will be precise.

Idea of IW is simmilar to ROB, but they are few differences:
- ROB is not a part of context
- ROB remove instructions in-order, IW allow to remove instructions out-of-order
- Tags in IW are in one-hot-encoding, which will in current implementation cause big overhead.

So in its original form IW is unfeasible for our processor, because it would require to double a ROB. Additionally this
context of the ROB size will have to be stored on each entry to interrupt hander which can be costly operations.
But:
- maybe its is possible to reduce cost of IW saving by cooperation of CPU and OS?
- maybe cost of restoring IW is smaller than cost of re-fetching and scheduling one more time old instructions?


Some interesting ideas from the paper:
- they propose NRP (No Return Point) implementation - a point in pipeline after which instruction can cot be removed, it
  should allow instructions which are ending to save its results and remove itself from IW, to don't waste cycles on
  context restore for executing this instruction one more time, NRP can be implemented for different interrupts and
  instructions in different places to allow different interrupt latency
- for vector instructions IW remember how many elements are left to be processed, so after context restore this allow to
  restore vector operation in the middle of vector


## In-Line Interrupt Handling for Software-Managed TLBs

> In-Line Interrupt Handling for Software-Managed TLBs
> Aamer Jaleel and Bruce Jacob, 2001

In that time ROBs where already a standard, so there is a "classic" interrupt handling procedure. But in that time there
is still a lot of software managed TLBs, which cause interrupt on each page miss. This of course cause a big penalty, so
authors of this paper try to reduce interrupt penalty. As a base architecture they use Alpha and MIPS. They concentrate
of improving TLB miss efficiency and this has a property that interrupt handlers are very short (10-30 instructions).

Main idea is to don't flush whole pipeline on interrupt, but instead to inline a handler code between instructions of
user space program. They observed, that the most important problem is that there can be not enough resources to execute
interrupt handler without flushing pipeline (e.g. in case when ROB is full there can be live-lock). 
- they assume that interrupt handler has known length
- they check if ROB, RS and FreeRF have enough free resources to inline handler
- if the handler can be inlined, they do that, else they flush pipeline
- in fly interrupt return instruction is swaped to NOP and excepted instruction is reexecuted
- each executed instruction has connected one pit indicating privilege level

They use some properties of Alpha and MIPS architectures where they have interrupts vectors so the OS can insert short,
specific, handlers to correct interrupt vector addresses. Contrary to that in current design it is a tendency to have one
interrupt handler in OS, which next decide which handling functions should be invoke. This make handler longer, so it
can be hard to make inlining (e.g for riscV in Linuks first step is to save each 32 general purpose registers, so on the
start we have 32 instructions in handler)

Interesting ideas from paper:
- Pipeline don't have to be flushed
- Additional HW resources reserved only for privileged mode can allow to execute privileged instruction without
  boring with stopping userspace program
- Interrupts and exceptions can be treated as branches and can be speculated


## Hardware/software cost analysis of interrupt processing strategies:

> Hardware/software cost analysis of interrupt processing strategies:
> Mansur H. Samadzadeh, Loai E. Garalnabi, 2001

Present overview for all main structures to handle exceptions, so:
- Instruction Window
- Checkpoint repair
- History file
- Reorder buffer
- Future file

## iGPU: Exception Support and Speculative Execution on GPUs

> iGPU: Exception Support and Speculative Execution on GPUs
> Jaikrishnan Menon, Marc de Kruijf, Karthikeyan Sankaralingam, 2012

They try to introduce exception to GPU. To do that, they observe that:
- it is possible to find points where it is low number of live registers (e.g. boundaries of kernels)
- GPU execution has no site effects, so it can be safety replayed
- GPU program can be recompiled in runtime

They introduce to GPU program regions and subregions. Region is part of code which on the begging and on the end have
small number of live registers. Subregion is a part of region which has short length (no more than 32 instructions).
In each subregion there is no instruction which override output of the instruction from the previous subregion. Each
subregion end is and instruction barrier.

Exceptions and interrupts are handled by restarting execution of warp from the beginning of region. Wrong speculation is
handled by restarting execution of current subregion. In case when there are two exceptions in region, code is
dynamically recompiled and split into two regions to prevent live-locks.

## Efficient Exception Handling Support for GPUs

> Efficient Exception Handling Support for GPUs
> Ivan Tanasic, Isaac Gelado, Marc Jorda, Eduard Ayguade, Nacho Navarro, 2017

One more time it is analysed the problem of precise interrupts for GPU. They observe that the only problematic
instructions are this related with memory access. All other are guaranteed to end successfully or they error kill
program. This time there is more hardware modification and there are presented three propositions:
- stall warp until previous global load is solved - on GPU it is not so problematic because usually there is a lot of
  other warp which wait to be executed.
- save instructions which can fail (global load) to next replay them, input register are not allowed to be modified
  until this instruction don't claim that it doesn't fail
- operand logging - replay queue + storing operands

## Others

> Reducing Exception Management Overhead with Software Restart Markers
> Mark Jerome Hampton, 2008

Mention a paper of Alli and Bailey [AB04] where there is no ROB. Instead of that in RAT there are FIFO-s which store
mapping between physical and logical register and the age of instruction. If there is a need to rise an exception it is
checked if all younger instruction have already ended if not exception wait.


## Summary 

GPU research don't help us much, because the main assumption there is that operations don't cause side effects except
of communication with main memory by load/store instructions. From research about CPU it looks like, for ROB there is a
"canonical" implementation and there can be eventually introduced some small improvements, but there aren't any very
different procedures.
