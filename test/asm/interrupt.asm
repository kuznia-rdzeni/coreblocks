# fibonacci spiced with interrupt handler (also with fibonacci)
    li x30, 0     # interrupt count
    li x31, 0xde  # branch guard
    li x1, 0x100
    csrrw x0, mtvec, x1
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
    addi x30, x30, 1
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
