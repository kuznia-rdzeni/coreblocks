    la x1, handler
    csrw mtvec, x1
    li x8, 0
    li x7, 0x80000000 
c0:
    lw x1, 0x230(x7)
c1:
    ebreak
c2:
    j i_out_of_range
c3:
    j i_partial_out_of_range
c4:
.word 0x43
c5:
.word 0x8000
c6:
    csrr x1, 0x123
c7:
    csrwi 0x123, 8
c8:
    sw x1, 0x231(x7)
c9:
    ecall

pass:
    j pass


# TODO: check if mepc can misalign

handler:
    la x1, excpected_mtval
    add x1, x1, x8
    lw x2, (x1)
    csrr x1, mtval
    bne x1, x2, fail
    
    la x1, excpected_mcause
    add x1, x1, x8
    lw x2, (x1)
    csrr x1, mcause
    bne x1, x2, fail
    
    la x1, next_instr 
    add x1, x1, x8
    lw x2, (x1)
    csrw mepc, x2
    
    addi x8, x8, 4
    
    mret

fail:
    j fail

.org 0x0FFE 
# it is legal - C is enabled in core, but can't be enabled in toolchain to keep 4-byte nops 
i_partial_out_of_range:
nop
i_out_of_range:
nop

.data
excpected_mtval:
.word 0x80000230
.word c1 
.word i_out_of_range 
.word i_partial_out_of_range + 2 
.word 0x43 
.word 0x8000 
.word 0x123020f3 
.word 0x12345073 
.word 0x80000231
.word 0
excpected_mcause:
.word 5 
.word 3 
.word 1 
.word 1 
.word 2 
.word 2 
.word 2 
.word 2 
.word 6 
.word 11 
# testing misaligned instr branch is not possible with C enabled
next_instr:
.word c1
.word c2
.word c3
.word c4
.word c5
.word c6
.word c7
.word c8
.word c9
.word pass

