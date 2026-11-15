    li x15, 5 # this many instructions will raise an exception
    la x6, exception_handler
    csrw mtvec, x6 # set-up handler
    # perform a forward jump to trigger flushing
    mv x7, x6
    beq x6, x7, next
    nop
next:
    # I is present in misa, Y (reserved) is not
    csrr x1, misa
    li x2, (1 << 8) | (1 << 24)
    and x1, x1, x2
    li x2, (1 << 8)
    bne x1, x2, fail

    # test read-only CSRs
    csrw mvendorid, 1
    csrw marchid, 1
    csrw mimpid, 1
    csrw mhartid, 1
    csrw 0xf15, 1  # csrw mconfigptr, 1
    csrr x1, mvendorid
    csrr x2, marchid
    csrr x3, mimpid
    csrr x4, mhartid
    csrr x5, 0xf15  # csrr x5, mconfigptr
    # test writable CSRs
    csrw mscratch, 4
    csrr x6, mscratch
pass:
    csrw 0x8fe, 0x10
    j pass
fail:
    csrw 0x8fe, 0x12
    j .

exception_handler:
   addi x15, x15, -1 # count exceptions

   csrr x31, mepc    # resume program execution,
   addi x31, x31, 4   # but skip unimplemented instruction
   csrw mepc, x31
   mret
