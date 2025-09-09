_start:
    li x2, 0

    la x1, trap_handler
    csrw mtvec, x1

    li x1, 0b11 << 11
    csrs mstatus, x1 # Set transfer to Priv mode

    li x1, 0b11 << 3
    csrs mstatus, x1 # enable mstatus.MIE

    li x1, 1<<3
    csrs mie, x1 # enable MSI interrupt

    li x5, 1
    li x4, 0xE1000000
    sw x5, (x4) # trigger clint IPI

1:
    j 1b

    sw x5, (x4) # trigger clint IPI

1:
    j 1b

    li x5, 0x2
    li x6, 0x10
    li x4, 0xE1004000
    sb x5, 1(x4)
    sb x6, 0(x4) # set mtimecmp = 0x210

    li x1, 1<<7
    csrs mie, x1 # enable MTI interrupt

1:
    j 1b

t2c:

    # set mtime to 0xF_FFFF (mtimecmp = 0x10_0000)
    li x6, 0xf
    li x5, -1
    li x4, 0xE100BFF8
    sw x0, 0(x4)
    sw x6, 4(x4)
    sw x5, 0(x4)

1:
    j 1b

fail:
    sw x0, (x0)
    j fail

pass:
    li x8, 1
    j pass

trap_handler:
    addi x2, x2, 1

ipi_handler_0_1:
    addi x7, x2, -2
    bgtz x7, timer_handler_0

    li x4, 0xE1000000
    sw x0, (x4) # reset IPI

    csrr x1, mepc
    addi x1, x1, 4 # skip wait loop
    csrw mepc, x1

    mret # IPI interrupts

timer_handler_0:
    addi x7, x7, -1
    bgtz x7, timer_handler_1

    csrr x1, time
    addi x1, x1, -0x210
    bltz x1, fail
    addi x1, x1, -128
    bgtz x1, fail

    # don't reset - interrupt should re-trigger immediately (without executing next CLINT store)
    csrr x1, mepc
    addi x1, x1, 4 # skip wait loop
    csrw mepc, x1
    mret

timer_handler_1:
    addi x7, x7, -1
    bgtz x7, timer_handler_2

    # clear timer interrupt by setting high value of mtimecmp
    li x5, 0x10
    li x4, 0xE1004000
    sw x5, 4(x4)
    sw x0, 0(x4)

    la x1, t2c
    csrw mepc, x1

    mret

timer_handler_2:
    addi x7, x7, -1
    bgtz x7, fail

    csrr x1, time
    addi x1, x1, -128
    bgtz x1, fail

    csrr x1, timeh
    addi x1, x1, -0x10
    bnez x1, fail

    j pass
