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
