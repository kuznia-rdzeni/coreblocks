_start:
    .include "init_regs.s"

    li x1, 0x100 # set handler vector
    csrw mtvec, x1
    li x1, 0x10000 # enable custom interrupt 0
    csrw mie, x1
    csrsi mstatus, 0x8 # machine interrupt enable
    csrr x29, mstatus
    li x3, 0
loop:
    wfi
    beq x2, x3, loop
infloop:
    j infloop

handler:
    addi x30, x30, 1
    addi x27, x27, 1
    li x1, 0x10000
    csrc mip, x1 # clear edge reported interrupt
    beq x2, x3, skip
    addi x3, x3, 1
skip:
    mret

.org 0x100
    j handler
