.macro INIT_REGS_LOAD
# load the initial states of registers
# the value of a register `n` is assumed to be stored under address `0x100 + n * 4`.
    lw  x1, 0x104(x0)
    lw  x2, 0x108(x0)
    lw  x3, 0x10c(x0)
    lw  x4, 0x110(x0)
    lw  x5, 0x114(x0)
    lw  x6, 0x118(x0)
    lw  x7, 0x11c(x0)
    lw  x8, 0x120(x0)
    lw  x9, 0x124(x0)
    lw  x10,0x128(x0)
    lw  x11,0x12c(x0)
    lw  x12,0x130(x0)
    lw  x13,0x134(x0)
    lw  x14,0x138(x0)
    lw  x15,0x13c(x0)
    lw  x16,0x140(x0)
    lw  x17,0x144(x0)
    lw  x18,0x148(x0)
    lw  x19,0x14c(x0)
    lw  x20,0x150(x0)
    lw  x21,0x154(x0)
    lw  x22,0x158(x0)
    lw  x23,0x15c(x0)
    lw  x24,0x160(x0)
    lw  x25,0x164(x0)
    lw  x26,0x168(x0)
    lw  x27,0x16c(x0)
    lw  x28,0x170(x0)
    lw  x29,0x174(x0)
    lw  x30,0x178(x0)
    lw  x31,0x17c(x0)
.endm

.macro INIT_REGS_ALLOCATION
.section .init_regs, "a", @nobits
.skip 0x80
.previous
.endm
