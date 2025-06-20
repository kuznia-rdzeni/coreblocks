setup: # Allow access if no other rule matches
    li t0, 0xFFFFFFFF
    csrw pmpaddr60, t0
    li t0, 0b00001111 # TOR RWX
    csrw pmpcfg15, t0

# Data adress space:
# 0x0 - one
# 0x4 - two
li x1, 1
sw x1, 0(x0)
li x2, 2
sw x2, 4(x0)
.4byte 0  /* should be unimp, but it would test nothing since unimp is system and stalls the fetcher >:( */
sw x1, 4(x0)  /* TODO: actually check the side fx */
li x2, 9

.section .bss
.skip 0x8
