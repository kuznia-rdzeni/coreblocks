.section .text

_start:
    # Configure PMP to allow S-mode access if present
    li x1, 0x1F
    csrw pmpcfg0, x1
    li x1, -1
    csrw pmpaddr0, x1

    li x9, 0
    la x10, 0

    # Set up level 1 page table: PPN = level_0_page_table, V=1
    # index 0x142
    li x3, 0x2000  # address of level_1_page_table
    li x2, (3 << 10) | 0x1
    sw x2, (0x142 * 4)(x3)

    # Set up level 0 page table: PPN = data_page, V=1, R/W=1, A/D=1
    # index 0x093 and 0x157 (aliasing)
    li x3, 0x3000  # address of level_0_page_table
    li x2, (4 << 10) | 0xC7
    sw x2, (0x093 * 4)(x3)
    sw x2, (0x157 * 4)(x3)

    # Set up code page at 0x100 with V=1, X=1, A=1
    li x2, (1 << 10) | 0x49
    sw x2, (0x100 * 4)(x3)

    # Set SATP to SV32 mode (mode=1) with root PPN = level_1_page_table
    li x1, 2  # PPN of level_1_page_table
    li x2, 1  # mode = 1 for SV32
    slli x2, x2, 31
    or x1, x1, x2
    csrw satp, x1

    # check that we have successfully gotten satp written
    csrr x2, satp
    sub x2, x2, x1
    bnez x2, fail
    addi x9, x9, 1

    # Enter S-mode via MRET
    # virtual address of s_mode_main
    la x1, (0x142 << 22) | (0x100 << 12) | 0x000
    csrw mepc, x1
    # set MPP to S (01) and MIE to 0
    li x1, 0b11 << 11
    csrc mstatus, x1
    li x1, 0b01 << 11
    csrs mstatus, x1
    mret

.org 0x1000
s_mode_main:
    addi x9, x9, 1

    li x1, (0x142 << 22) | (0x093 << 12) | 0x000
    li x2, (0x142 << 22) | (0x157 << 12) | 0x000

    lw x3, 0(x1)
    lw x4, 0(x2)

    li x5, 0xDEADBEEF
    bne x3, x5, fail
    addi x9, x9, 1
    bne x4, x5, fail
    addi x9, x9, 1

    # check aliasing
    li x5, 0xCAFEBABE
    sw x5, 0(x1)
    lw x6, 0(x2)

    bne x6, x5, fail
    addi x9, x9, 1

    j success

success:
    la x10, 1
    j success

fail:
    j fail

.section .data
.org 0x2000
.space 4096
.org 0x3000
.space 4096
.org 0x4000
.word 0xDEADBEEF
.space 4096 - 4
