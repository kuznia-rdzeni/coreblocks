_start:
    # Configure PMP: allow all access for S-mode
    li x1, 0x1F
    csrw pmpcfg0, x1
    li x1, -1
    csrw pmpaddr0, x1

    li x31, 0xde

    la x1, machine_trap
    csrw mtvec, x1

    la x1, supervisor_trap
    csrw stvec, x1

    li x1, 1 << 17 # delegate custom level interrupt to supervisor mode
    csrw mideleg, x1

    li x1, 1 << 17
    csrw sie, x1

    # Set MPP to supervisor and transfer via MRET.
    li x1, 0b11 << 11
    csrc mstatus, x1
    li x1, 0b01 << 11
    csrs mstatus, x1

    la x1, s_mode_main
    csrw mepc, x1
    mret

s_mode_main:
    csrr x2, 0x8ff # custom testbench CSR - current privilege mode
    li x3, 1
    bne x2, x3, fail

    li x3, 1
    csrsi sstatus, 0x2 # set sstatus.SIE

wait_for_interrupt:
    beq x7, x3, after_interrupt
    j wait_for_interrupt

after_interrupt:
    csrr x10, sstatus
    andi x11, x10, 0x2
    beqz x11, fail

    li x5, 1
    j pass

supervisor_trap:
    addi x7, x7, 1

    csrr x8, scause
    li x9, 0x80000011
    bne x8, x9, fail

    # During trap handling: SIE must be cleared and SPIE should be set.
    csrr x10, sstatus
    andi x11, x10, 0x2
    bnez x11, fail

    andi x12, x10, 0x20
    beqz x12, fail

    sret

machine_trap:
    # M-mode trap handler must not fire in this test (interrupt is delegated)
    li x31, 0xae

fail:
    j fail

pass:
    j pass
