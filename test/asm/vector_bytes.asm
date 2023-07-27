initMem:
    # Initialise first 256 bits of memory
    li x1, 1
    sw x1, 0(x0)
    li x1, 2
    sw x1, 4(x0)
    li x1, 5
    sw x1, 8(x0)
    li x1, 10
    sw x1, 12(x0)
    li x1, 3
    sw x1, 16(x0)
    li x1, 0
    sw x1, 20(x0)
    li x1, 14
    sw x1, 24(x0)
    li x1, 42
    sw x1, 28(x0)
byteDataInit:
    li x1, 30
    sb x1, 5(x0)
    li x1, 25
    sb x1, 6(x0)
    li x1, 255
    sb x1, 21(x0)
    li x1, 181
    sb x1, 29(x0)
    li x1, 15
    sb x1, 30(x0)
    vsetivli x0, 31, e8,m1,ta,ma
    vle8.v v3, (x0)
    vadd.vi v2, v3, 0
    vsetivli x0, 30, e8,m1,tu,ma
    li x1, 9 # loop counter
byteLoop:
    vadd.vv v3, v3, v2
    addi x1, x1, -1
    bne x1, x0, byteLoop
    li x1, 32
    li x2, 0x55
    sb x2, 63(x0)
    vsetivli x0, 31, e8,m1,ta,ma
    vse8.v v3, (x1)
getFromMem:
    lw x1, 32(x0)
    lw x2, 36(x0)
    lw x3, 40(x0)
    lw x4, 44(x0)
    lw x5, 48(x0)
    lw x6, 52(x0)
    lw x7, 56(x0)
    lw x8, 60(x0)
    lw x9, 64(x0)
infloop:
    j infloop

