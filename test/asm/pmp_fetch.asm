_start:
    la x1, trap_handler
    csrw mtvec, x1

    # PMP Entry 0: [0, 0x10000), TOR, RWX
    li x1, 0x10000 >> 2
    csrw pmpaddr0, x1
    li x1, 0b00001111
    csrw pmpcfg0, x1

    li x1, 0b11 << 11
    csrc mstatus, x1  # Set transfer to User mode to mpp

    la x1, user_code
    csrw mepc, x1
    mret              # Go to user_code in user mode

user_code:
    li x1, 0x20000
    jalr x0, x1, 0 # Jump to address outside PMP region
    j fail

trap_handler:
    csrr x1, mcause
    li x2, 1
    bne x1, x2, fail  # Check if it is a ACCESS fault
    j pass

fail:
    j fail

pass:
    li x1, 1
    j pass
