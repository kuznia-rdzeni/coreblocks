# fibonacci spiced with interrupt handler (also with fibonacci)
    li x1, 0x100
    csrw mtvec, x1
    li x30, 0     # interrupt count
    li x31, 0xde  # branch guard
    csrsi mstatus, 0x8 # machine interrupt enable
    li x1, 0x30000
    csrw mie, x1 # enable custom interrupt 0 and 1
    li x1, 0
    li x2, 1
    li x5, 4
    li x6, 7
    li x7, 0
loop:
    add x3, x2, x1
    mv x1, x2
    mv x2, x3
    bne x2, x4, loop
infloop:
    j infloop

int_handler:
    # save main loop register state
    mv x9, x1
    mv x10, x2
    mv x11, x3

    # clear interrupts
    csrr x1, mip
    srli x1, x1, 16
    andi x2, x1, 0x1
    beqz x2, skip_clear_edge
        li x2, 0x10000
        csrc mip, x2 # clear edge reported interrupt
        addi x30, x30, 1
    skip_clear_edge:
    andi x2, x1, 0x2
    beqz x2, skip_clear_level
        csrwi 0x7ff, 1 # clear level reported interrupt via custom csr
        addi x30, x30, 1
    skip_clear_level:

    # load state
    mv x1, x5
    mv x2, x6
    mv x3, x7
    # fibonacci step
    beq x3, x8, skip
    add x3, x2, x1
    mv x1, x2
    mv x2, x3
    # store state
    mv x5, x1
    mv x6, x2
    mv x7, x3
skip:
    # restore main loop register state
    mv x1, x9
    mv x2, x10
    mv x3, x11
    mret

.org 0x100
    j int_handler
    li x31, 0xae  # should never happen
