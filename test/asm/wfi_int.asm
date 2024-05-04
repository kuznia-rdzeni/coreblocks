    li x1, 0x100
    csrw mtvec, x1
    li x3, 0
loop:
    wfi
    beq x2, x3, loop
infloop:
    j infloop

handler:
    addi x30, x30, 1
    beq x2, x3, skip
    addi x3, x3, 1
skip:
    mret

.org 0x100
    j handler
