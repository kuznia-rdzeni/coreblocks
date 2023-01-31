    li x2, 1
    li x4, 2971215073 # last fibonacci number to fit in 32 bits
loop:
    add x3, x2, x1
    mv x1, x2
    mv x2, x3
    bne x2, x4, loop
infloop:
    j infloop
