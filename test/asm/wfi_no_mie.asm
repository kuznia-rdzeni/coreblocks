_start:
    li x4, 0

    la x1, trap_handler
    csrw mtvec, x1

    li x1, 1<<17
    csrs mie, x1 # enable fixed level interrupt
    # but keep mstatus.MIE disabled

    li x2, 1
    loop:
        wfi
        addi x2, x2, -1
        bnez x2, loop

    j pass

fail:
    j fail

pass:
    li x8, 8
    j pass

trap_handler:
    j fail
