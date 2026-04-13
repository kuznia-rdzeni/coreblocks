# User mode test
# runs `user_code`* in user mode that ends with control transfer via excpetion
# or interrupt to trap_handler.
# trap_handler verifies trap cause and priv mode change

_start:
    li x4, 0

    la x1, trap_handler
    csrw mtvec, x1

    li x2, 0b11 << 11
    csrc mstatus, x2
    li x2, 0b10 << 11  # set mpp to invalid value
    csrs mstatus, x2

    li x5, 0b00 << 11  # expected mpp value for trap handler to verify
    la x1, user_code
    csrw mepc, x1
    mret # go to user_code in user mode

user_code:
    # case0 - test ecall from user mode
    csrr x1, 0x8FF # custom testbech CSR - check current priv mode
    bnez x1, fail # user mode = 0

    ecall

    j fail

supervisor_code2:
    # case1 - standard interrupt entry from supervisor mode
    # case2 - wfi should be illegal in supervisor mode when mstatus.TW is set
    wfi
    j fail

user_code3:
    # case3 - test write to CSR not accesible from user mode
    csrr x1, mstatus
    j fail

user_code4:
    # case4 - wfi is illegal in user mode
    wfi
    j fail

fail:
    j fail

pass:
    j pass

set_mpp_umode:
    # setup expected mpp value for trap handler to verify
    li x5, 0b00 << 11
    li x2, 0b11 << 11
    csrc mstatus, x2
    csrs mstatus, x5
    ret

set_mpp_smode:
    # setup expected mpp value for trap handler to verify
    li x5, 0b01 << 11
    li x2, 0b11 << 11
    csrc mstatus, x2
    csrs mstatus, x5
    ret

trap_handler:
    csrr x1, mstatus
    li x2, 0b11 << 11
    and x1, x1, x2 # mpp
    bne x1, x5, fail

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

    # mstatus.MIE = 0, but interrupts are active in lower modes (when enabled in mie)

    call set_mpp_smode
    la x1, supervisor_code2
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

    call set_mpp_smode
    la x1, supervisor_code2
    csrw mepc, x1
    mret

case2:
    addi x3, x3, -1
    bgtz x3, case3

    csrr x1, mcause
    li x2, 2 # ILLEGAL_INSTRUCTION
    bne x1, x2, fail

    li x1, 1<<21
    csrc mstatus, x1 # clear TW

    call set_mpp_umode
    la x1, user_code3
    csrw mepc, x1
    mret

case3:
    addi x3, x3, -1
    bgtz x3, case4

    csrr x1, mcause
    li x2, 2 # ILLEGAL_INSTRUCTION
    bne x1, x2, fail

    call set_mpp_umode
    la x1, user_code4
    csrw mepc, x1
    mret

case4:
    csrr x1, mcause
    li x2, 2 # ILLEGAL_INSTRUCTION
    bne x1, x2, fail

    addi x4, x4, 1
    j pass
