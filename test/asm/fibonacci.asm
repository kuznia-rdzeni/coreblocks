    addi x2, x2, 1
    li x4, 2971215073 # last fibonacci number to fit in 32 bits
loop:
    add x3, x2, x1
    add x1, x0, x2
    add x2, x0, x3
    bne x2, x4, loop
infloop:
    beq x0, x0, infloop
