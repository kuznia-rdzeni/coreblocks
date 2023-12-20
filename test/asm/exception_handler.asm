    li x2, 1
    li x4, 987 # target fibonnaci number
    li x15, 0

    la x6, exception_handler
    csrw mtvec, x6 # set-up handler
loop:
    add x3, x2, x1
.4byte 0  # raise exception without stalling the fetcher
    mv x1, x2
    mv x2, x3
    bne x2, x4, loop

    # report another exception after full rob_idx overflow
    # so it has the same rob index as previous report
    li x10, 0
    li x11, 13
rob_loop:
    addi x10, x10, 1
    nop
    nop
    nop
    nop
    nop
    nop
    bne x10, x11, rob_loop

    nop
    nop
    nop
    nop
    nop
    nop
    nop

.4byte 0 # exception

    li x11, 0xaaaa # verify exception return

infloop:
    j infloop

exception_handler:
   mv x6, x2
   li x2, 42 # do some register activity
   mv x2, x6

   addi x15, x15, 1 # count exceptions

   csrr x6, mepc    # resume program execution,
   addi x6, x6, 4   # but skip unimplemented instruction
   jr x6
