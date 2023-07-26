initMem:
    # Initialise first 256 bits of memory with 32-bits values
    li x1, 1
    sb x1, 0(x0)
    li x1, 2
    sb x1, 4(x0)
    li x1, 5
    sb x1, 8(x0)
    li x1, 10
    sb x1, 12(x0)
    li x1, 3
    sb x1, 16(x0)
    li x1, 0
    sb x1, 20(x0)
    li x1, 14
    sb x1, 24(x0)
    li x1, 42
    sb x1, 28(x0) # done at cycle ~235
doVectorOperations:
    vsetivli x0, 8, e32,m1,ta,ma
    # Load 8 first 32-bits elements from address 0 from memory to registers v0 and v1
    vle32.v v0, (x0)
    vle32.v v1, (x0)
    vadd.vv v2, v0, v0
    vadd.vv v2, v2, v1
    # Store vector on addresses from byte 32 to check interleaving of vector and
    # scalar instructions. Value "32" is calculated as a sacalar sum
    li x20, 11
    li x21, 21
    add x1, x20, x21
    # Add a canary on first entry which shouldn't be modified
    li x20, 0xDEADBEEF
    sb x20, 64(x0)
    vse32.v v2, (x1)
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
