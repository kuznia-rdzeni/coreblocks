li x1, -1
csrw mcycleh, x1
nop
nop
nop
nop
csrw mcycle, x1
nop
nop
nop
nop
csrr x2, mcycle
li x5, 100
bgt x2, x5, fail
csrr x2, mcycleh
bnez x2, fail

pass:
csrwi 0x8fe, 0x10
j .

fail:
csrwi 0x8fe, 0x12
j .
