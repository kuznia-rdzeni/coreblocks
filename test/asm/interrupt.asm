# fibonacci spiced with interrupt handler
    li x1, 0x100
    csrrw x0, mtvec, x1
    li x1, 0
    li x2, 1
    li x4, 89 # small fibonacci number to keep execution time to a minimum
loop:
    add x3, x2, x1
    mv x1, x2
    mv x2, x3
    bne x2, x4, loop
infloop:
    nop
    j infloop

int_handler:
    # execute some dummy instructions
    li x5, 420
    li x6, 1337
    li x7, -42
    li x8, 38
do_ops:
    add x5, x5, x6
    xor x6, x5, x7
    sub x7, x5, x6
    and x6, x7, x6
    slli x6, x6, 3 
    blt x0, x6, do_ops
    mret

.org 0x100
    j int_handler
