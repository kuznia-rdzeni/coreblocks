# Summary of papers about interrupts

## Introduction

This summary is a result of analysis of journal articles which I made as a preparation to implement support for
interrupts, exceptions and speculation to core blocks. It looks like the choice of primary interrupts related to
structure determines the interrupt handling procedure. We have chosen a ROB, so there is a one classical implementation
of the ROB interrupt handling procedure. This procedure is used as a basis for the improvements, but most of the papers
are pretty old (1993-2001). Currently there is no much research going on about CPU interrupt handling and it is
considered that this problem is solved. Instead of that, there are some works, which try to implement precise interrupts
on GPUs, but due to different characteristics of the CPU and GPU, this research can not be applied in an easy way to our
project.

When I have prepared this overview, I have decided to look at articles from different times to check on what people were
working at that time. So there is probably a lot of other works which can be worth checking out. Specifically:
- W. Walker and H. G. Cragon. “Interrupt processing in concurrent processors.” IEEE Computer, vol. 28, no. 6, June 1995
- M. Moudgill and S. Vassiliadis. “Precise interrupts.” IEEE Micro, vol. 16, no. 1, pp. 58–67, February 1996
These two works present a survey of the topic of interrupts as a time of writing.

## Interrupt handling in old PCs

- CDC 6600 - interrupt handling is done by inserting a jump instruction into the interrupt handler 
- IBM360 - stop fetching and wait for all fetched instructions to be committed, then jump to interrupt handler 
- CRAY-1 - similar to IBM360, but here latency can be even bigger due to vector instructions

## Interrupt Handling for Out-of-Order Execution Processors

> Interrupt Handling for Out-of-Order Execution Processors
> H. C. Torng and Martin Day, 1993

This article describes one of the first probes for the implementation of exceptions in out-of-order processes. In that
time, ROB was a very new idea. The authors of this paper introduced Instruction Window (IW) as their proposition for the
implementation of interrupts in out-of-order processors. IW will store all dispatched instructions, which didn't
complete. In the case of an interrupt it will be a part of the context and will be copied to memory by the interrupt handler.
After restoring the context, all instructions from IW will be restarted so that the state of the CPU will be precise.

The idea of IW is similar to that of ROB, but there are few differences:
- ROB is not a part of the context
- ROB removes instructions in-order, IW allows to remove instructions out-of-order 
- Tags in IW are one-hot-encoded, which will in current implementation cause big overhead.

So in its original form, IW is unfeasible for our processor, because it would require to double a job. Additionally,
this context of the ROB size will have to be stored on each entry to the interrupt handler, which can be costly
operations. But: 
- maybe it is possible to reduce cost of IW saving by cooperation of CPU and OS? 
- maybe cost of restoring IW is smaller than cost of re-fetching and scheduling one more time for old instructions?

Some interesting ideas from the paper: 
- they propose NRP (No Return Point) implementation - a point in the pipeline after which an instruction can be removed,
    it should allow instructions which are ending to save its results and remove itself from IW, to don't waste cycles on
    context restore for executing this instruction one more time, NRP can be implemented for different interrupts and
    instructions in different places to allow different interrupt latency 
- for vector instructions IW remember how many elements are left to be processed, so after this context restore allows
    to restore vector operation in the middle of the vector


## In-Line Interrupt Handling for Software-Managed TLBs

> In-Line Interrupt Handling for Software-Managed TLBs 
> Aamer Jaleel and Bruce Jacob, 2001

In that time, ROB was already a standard, so there was "classic" interrupt handling procedure. But in that time
there is still a lot of software managed TLBs, which cause an interrupt on each page miss. This of course causes a big
context switch overhead, so the authors of this paper try to reduce this penalty. As a base architecture they use Alpha and MIPS. They
concentrate on improving TLB miss efficiency and this has a property that interrupt handlers are very short (10-30
instructions).

The main idea is to not flush the whole pipeline on an interrupt, but instead to inline a handler code between
instructions of the user space program. They observed that the most important problem is that there can not be enough
resources to execute the interrupt handler without flushing the pipeline (e.g. in case when ROB is full there can be
live-lock). 
- they assume that interrupt handler has known length 
- they check if ROB, RS and RF have enough free resources to inline handler 
- if the handler can be inlined, they do that, else they flush the pipeline 
- in fly instruction return instruction is swapped to NOP and excepted instruction is reexecuted 
- each executed instruction has one connected bit indicating the privilege level

They use some properties of the Alpha and MIPS architectures where they have interrupts vectors so the OS can insert
short, specific, handlers to correct the interrupt vector addresses. In contrast to that in current design it is a
tendency to have one interrupt handler in OS, which next decides which handling functions should be invoked. This makes
the handler longer, so it can be hard to make inlining (e.g. for risk V in Linux the first step is to save
each of general purpose registers, so on the start we have already 32 instructions in handler)

Ideas from the paper: 
- Pipelines don't have to be flushed 
- Additional HW resources reserved for only privileged mode can allow to execute privileged instruction without boring
  with stopping user space program 
- Interrupts and exceptions can be treated as branches and can be speculated


## Hardware/software cost analysis of interrupt processing strategies:

> Hardware/software cost analysis of interrupt processing strategies
> Mansur H. Samadzadeh, Loai E. Garalnabi, 2001

Present overview for all main structures to handle exceptions, so:
- Instruction Window
- Checkpoint repair
- History file
- Reorder buffer
- Future file

## iGPU: Exception Support and Speculative Execution on GPUs

> iGPU: Exception Support and Speculative Execution on GPUs Jaikrishnan Menon, Marc de Kruijf, Karthikeyan
> Sankaralingam, 2012

They try to introduce exceptions to GPU. To do that, they observe that: 
- it is possible to find points where it is low number of live registers (e.g., boundaries of kernels) 
- GPU execution has no side effects, so it can be safely rewritten 
- GPU program can be recompiled in runtime

They introduce to the GPU program regions and subregions. Regions are parts of code which start at the beginning and end
with a small number of live registers. Subregion is a part of a region which has short length (not more than 32
instructions). In each subregion there is no instruction which overrides the output of the instruction from the previous
subregion. Each subregion end is an instruction barrier.

Exceptions and interrupts are handled by restarting execution of warp from the beginning of region. Wrong speculation is
handled by restarting execution of current subregion. In case when there are two exceptions in region, code is
dynamically recompiled and split into two regions to prevent live-locks.


## Efficient Exception Handling Support for GPUs

> Efficient Exception Handling Support for GPUs 
> Ivan Tanasic, Isaac Gelado, Marc Jorda, Eduard Ayguade, Nacho Navarro, 2017

One more time it is analysed the problem of precise interrupts for GPU. They observe that the only problematic
instructions are those related to memory access. All other instructions are guaranteed to end successfully or they kill
the program. This time there is more hardware modification and there are presented three propositions: 
- stall warp until previous global load is solved - on GPU it is not so problematic because usually there is a lot of
    other warp which wait to be executed.  
- save instructions which can fail (global loads) to next reply them, input registers are not allowed to be
    modified until this instruction don't claim that it doesn't fail 
- operand logging - replay queue + storing operations


## Others

> Reducing Exception Management Overhead with Software Restart Markers
> Mark Jerome Hampton, 2008

Mention a paper of Alli and Bailey [AB04] where there is no ROB. Instead of that in RAT there are FIFO-s which store
mapping between physical and logical registers and the age of instruction. If there is a need to raise an exception it
is checked if all younger instruction have already ended if not an exception wait for some cycles and repeat the check.


## Summary

GPU research don't help us much, because the main assumption is that operations don't cause side effects
except of communication with main memory by load/store instructions. From research about CPUs, it looks like,
there is a "canonical" implementation of ROB that can be eventually introduced some small improvements, but
there aren't any very different procedures.
