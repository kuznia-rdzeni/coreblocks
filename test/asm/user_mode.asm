_start:
    li x4, 0

    la x1, trap_handler
    csrw mtvec, x1
    
    li x1, 0b11 << 11
    csrc mstatus, x1 # User mode to mpp

    la x1, user_code
    csrw mepc, x1
    mret # go to user mode

user_code:
    csrr x1, 0x8FF # custom - current priv mode
    bnez x1, fail

    ecall

    j fail
    
user_code2:
    wfi
    j fail

user_code3:
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

    # MIE = 0, but interrupts are active in U-MODE (when enabled in mie)

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
   
