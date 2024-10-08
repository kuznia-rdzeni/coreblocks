# User mode test
# runs `user_code`* in user mode that ends with control transfer via excpetion
# or interrupt to trap_handler.
# trap_handler verifies trap cause and priv mode change

_start:
    li x4, 0

    la x1, trap_handler
    csrw mtvec, x1

    li x1, 0b11 << 11
    csrc mstatus, x1 # Set transfer to User mode to mpp

    li x1, 0b10 << 11
    csrs mstatus, x1 # Invalid mpp mode, check if write is ignored

    la x1, user_code
    csrw mepc, x1
    mret # go to user_code in user mode

user_code:
    # case0 - test ecall from user mode
    csrr x1, 0x8FF # custom testbech CSR - check current priv mode
    bnez x1, fail # user mode = 0

    ecall

    j fail

user_code2:
    # case1 - standard interrupt entry from user mode
    # case2 - wfi should be illegal in user mode when mstatus.TW is set
    wfi
    j fail

user_code3:
    # case3 - test write to CSR not accesible from user mode
    csrr x1, mstatus
    j fail

fail:
    j fail

pass:
    j pass

trap_handler:
    csrr x1, mstatus
    li x2, 0b11 << 11
    and x1, x1, x2 # mpp
    bnez x1, fail

    csrr x1, 0x8FF # custom - current priv mode
    li x2, 0b11 # machine mode
    bne x1, x2, fail

    addi x4, x4, 1

case0:
    addi x3, x4, -1
    bgtz x3, case1

    csrr x1, mcause
    li x2, 8 # ECALL_FROM_U
    bne x1, x2, fail

    li x1, 1<<17
    csrs mie, x1 # enable fixed level interrupt

    # mstatus.MIE = 0, but interrupts are active in U-MODE (when enabled in mie)

    la x1, user_code2
    csrw mepc, x1
    mret

case1:
    addi x3, x3, -1
    bgtz x3, case2

    csrr x1, mcause
    li x2, 0x80000011 # interrupt 17
    bne x1, x2, fail

    li x1, 1<<21
    csrs mstatus, x1 # enable TW

    la x1, user_code2
    csrw mepc, x1
    mret

case2:
    addi x3, x3, -1
    bgtz x3, case3

    csrr x1, mcause
    li x2, 2 # ILLEGAL_INSTRUCTION
    bne x1, x2, fail

    la x1, user_code3
    csrw mepc, x1
    mret

case3:
    csrr x1, mcause
    li x2, 2 # ILLEGAL_INSTRUCTION
    bne x1, x2, fail

    addi x4, x4, 1
    j pass
