nop
rdinstret x1
nop
nop
rdinstret x2

pass:
csrw 0x8fe, 0x10
j pass
