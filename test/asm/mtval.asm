# test `mtval` and `mcause` CSR values for various excpetions 
# C extension is required in the core, but must be disabled in the toolchain

    la x1, handler
    csrw mtvec, x1
    li x8, 0

setup: # Allow access if no other rule matches
    li t0, 0xFFFFFFFF
    csrw pmpaddr60, t0
    li t0, 0b00001111 # TOR RWX
    csrw pmpcfg15, t0

    li x7, 0x80000000
c0: # load from illegal address. mtval=addr mcause=LOAD_ACCESS_FAULT 
    lw x1, 0x230(x7)
c1: # mtval=pc mcause=BREAKPOINT
    ebreak
c2: # instruction address out of memory mtval=i_out_of_range mcause=INSTRUCTION_ACCESS_FAULT
    j i_out_of_range
c3: # jump to 2-byte aligned, 4-byte long instruction, of which first two bytes are available 
    # and other half is outside of memory range. mtval=i_partial_out_of_range+2 mcause=INSTRUCTION_ACCESS_FAULT
    j i_partial_out_of_range
c4: # illegal 4-byte instruction ([0:2] = 0b11) mtval=raw instruction mcause=ILLEGAL_INSTRUCTION
.word 0x43
c5: # illegal compressed type ([0:2] != 0b11) instruction mtval=raw instruction mcause=ILLEGAL_INSTRUCTION
.word 0x8000
c6: # access to missing csr mtval=raw instruction mcause=ILLEGAL_INSTRUCTION
    csrr x1, 0x123
c7: # access to missing csr mtval=raw instruction mcause=ILLEGAL_INSTRUCTION
    csrwi 0x123, 8
c8: # store to misaligned address mtval=addr mcause=STORE_ADDRESS_MISALIGNED
    sw x1, 0x231(x7)
c9: # mtval=0 mcause=ENVIRONMENT_CALL_FROM_M 
    ecall

pass:
    j pass


handler: # test each case. test case number = in x8>>2
    la x1, expected_mtval
    add x1, x1, x8
    lw x2, (x1)
    csrr x1, mtval
    bne x1, x2, fail
    
    la x1, expected_mcause
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

# it is legal - C is enabled in core, but can't be enabled in toolchain to keep 4-byte nops 
.org 0x0FFE 
i_partial_out_of_range:
nop
i_out_of_range:
nop

.data

expected_mtval:
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

expected_mcause:
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
# testing misaligned instr branch is not possible with C enabled :(

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

