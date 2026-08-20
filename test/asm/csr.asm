nop
rdinstret x1
nop
beq x1, x1, 1f # trigger misprediction
nop
1:
rdinstret x2

pass:
csrw 0x8fe, 0x10
j pass
