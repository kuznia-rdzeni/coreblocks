setup: # Allow access if no other rule matches
    li t0, 0xFFFFFFFF
    csrw pmpaddr60, t0
    li t0, 0b00001111 # TOR RWX
    csrw pmpcfg15, t0

# Data adress space:
# 0x0 - fn-2
# 0x4 - fn-1
# 0x8 - target
clearDataMem:
    sb x0, 0(x0)
    sb x0, 4(x0)
initMem:
    li x2, 1
    sb x2, 4(x0)
    li x2, 55 # fib(10)
    sw x2, 8(x0)
loop:
    # collect data from memory
    lw x1, 0(x0)
    lw x2, 4(x0)
    # generate next fibonacci number
    add x3, x2, x1
    # store data in memory
    sw x2, 0(x0)
    sw x3, 4(x0)
    # compare with expected result
    lw x4, 8(x0)
    bne x3, x4, loop
infloop:
    j infloop

.section .bss
.skip 0xC
