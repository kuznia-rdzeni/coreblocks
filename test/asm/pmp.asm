setup: # Allow access if no other rule matches
    li t0, 0xFFFFFFFF
    csrw pmpaddr60, t0
    li t0, 0b00001111 # TOR RWX
    csrw pmpcfg15, t0

    la x1, handler
    csrw mtvec, x1
    li x8, 0

### MACHINE MODE TESTS

c0:
    li t0, 0x20000
    csrw pmpaddr3, t0
    li t0, 0x80001000
    csrw pmpaddr4, t0
    li t0, 0b1000              # TOR, R/W/X none
    csrw pmpcfg1, t0
    li x1, 0x30004
    li x2, 0xDEADC0DE
    sw x2, 0(x1)
    ecall

pass:
    j pass

handler:
    la x1, expected_mtval
    add x1, x1, x8
    lw x2, 0(x1)

    la x4, expected_mcause
    add x4, x4, x8
    lw x5, 0(x4)

    csrr x6, mcause
    csrr x7, mtval

    bne x2, x6, fail
    bne x5, x7, fail

    la x1, next_instr
    add x1, x1, x8
    lw x2, 0(x1)
    csrw mepc, x2
    addi x8, x8, 4
    mret

fail:
    j fail

.data
.org 0x4000
expected_mtval:
    .word 0x80000004

expected_mcause:
    .word 7     # load access fault

next_instr:
    .word pass

