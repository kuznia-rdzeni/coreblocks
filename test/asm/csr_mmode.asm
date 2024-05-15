    li x15, 5 # this many instructions will raise an exception
    la x6, exception_handler
    csrw mtvec, x6 # set-up handler
    # test read-only CSRs
    csrw mvendorid, 1
    csrw marchid, 1
    csrw mimpid, 1
    csrw mhartid, 1
    csrw mconfigptr, 1
    csrr x1, mvendorid
    csrr x2, marchid
    csrr x3, mimpid
    csrr x4, mhartid
    csrr x5, mconfigptr
    # test writable CSRs
    csrw mscratch, 4
    csrr x6, mscratch
infloop:
    j infloop

exception_handler:
   addi x15, x15, -1 # count exceptions

   csrr x31, mepc    # resume program execution,
   addi x31, x31, 4   # but skip unimplemented instruction
   csrw mepc, x31
   mret
