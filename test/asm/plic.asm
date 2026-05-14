# PLIC test, writes to CSR set PLIC interrupt input
# context 0 - MEI, context 1 - SEI

# plic base - 0xe2000000

# trigger interrupt
csrwi 0x7ff, 0b010

# disable timer interrupts
li x1, -1
li x4, 0xE1004000
sw x1, 0x4(x4)

li x16, 0xe2001000 # plic pending reg
lw x1, (x16)
li x2, 0b10 # irq 1 pending
bne x1, x2, fail

li x16, 0xe2200000 # claim reg ctx 0
lw x1, 0x4(x16)
bne x1, x0, fail

# plic enable bit for irq 1, ctx 0
li x1, 0b10
li x16, 0xe2002000
sw x1, (x16)

li x16, 0xe2200004 # claim reg ctx 0
lw x1, (x16)
bne x1, x0, fail

li x16, 0xe2001000 # plic pending reg
lw x1, (x16)
li x2, 0b10 # plic irq 1 pending
bne x1, x2, fail

# set positive int 1 priority
li x1, 1
li x16, 0xe2000000
sw x1, 0x4(x16)

li x16, 0xe2200000
lw x1, 0x4(x16) # claim reg, ctx 0
li x2, 1 # claim irq 1 successful
bne x1, x2, fail

li x16, 0xe2001000 # plic pending reg
lw x1, (x16)
bne x1, x0, fail  # no plic irqs pending

li x16, 0xe2200000
lw x1, 0x4(x16) # claim for ctx 0 should fail
bne x1, x0, fail

li x1, 2 # complete some other id
sw x1, 0x4(x16) # complete reg, ctx 0

li x16, 0xe2001000 # plic pending reg
lw x1, (x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

li x16, 0xe2200000
li x1, 1 # complete irq 1
sw x1, 0x4(x16) # complete reg, ctx 0
bne x1, x2, fail

li x16, 0xe2001000 # plic pending reg
lw x1, (x16)
li x2, 0b10 # should be pending again because external signal still high
bne x1, x2, fail

csrr x1, mip
li x2, 1 << 11
bne x1, x2, fail # MEI should be pending

# increase context 0 priority treshold
li x1, 1
li x16, 0xe2200000
sw x1, (x16)

1:
csrr x1, mip
bne x1, x0, 1b # wait until no interrupts pending

li x16, 0xe2201000
lw x1, 0x4(x16) # claim for ctx 1 should fail
bne x1, x0, fail

# plic enable bit for irq 1, ctx 1
li x1, 0b10
li x16, 0xe2002080
sw x1, (x16)

1:
csrr x1, mip
li x2, 1 << 9
bne x1, x2, 1b # SEI should be pending

li x16, 0xe2200000
# claim for ctx 0 should complete
# priority treshold only affect interrupt pending signal but not claim
lw x1, 0x4(x16)
li x2, 1 # claim irq 1 successful
bne x1, x2, fail

li x1, 1 # complete
sw x1, 0x4(x16) # complete reg, ctx 0

li x16, 0xe2201000
lw x1, 0x4(x16) # claim reg, ctx 1
li x2, 1 # claim irq 1 successful
bne x1, x2, fail

li x16, 0xe2001000
lw x1, (x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

# plic disable bit for irq 1, ctx 0
li x16, 0xe2002000
sw x0, (x16)

# completion from disabled id should be ignored
li x1, 1
li x16, 0xe2200000
sw x1, 0x4(x16) # complete reg, ctx 0

li x16, 0xe2001000
lw x1, (x16)
bne x1, x0, fail # no plic irqs pending (if it would succeed then gateway would be unlocked)

li x1, 1
li x16, 0xe2201000
sw x1, 0x4(x16) # complete reg, ctx 1

li x16, 0xe2001000
lw x1, (x16)
li x2, 0b10 # plic irq 1 pending
bne x1, x2, fail

csrw 0x7ff, x0 # disable interrupt source

li x16, 0xe2201000
lw x1, 0x4(x16)
li x1, 1
sw x1, 0x4(x16) # claim/complete reg, ctx 1

li x16, 0xe2001000
lw x1, (x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

li x1, 0b11110
csrw 0x7ff, x1 # enable interrupt sources

# set enables
li x16, 0xe2002000
sw x1, (x16) # enables ctx0
sw x1, 0x80(x16) # enables ctx1

# reset context 0 priority treshold
li x16, 0xe2200000
sw x0, (x16)

# set higher int 2 priority
li x1, 2
li x16, 0xe2000000
sw x1, 0x8(x16)

# set int 3,4 priority same as int 1
li x1, 1
sw x1, 0xc(x16)
sw x1, 0x10(x16)

li x16, 0xe2200000
lw x1, 0x4(x16) # claim reg, ctx 0
li x2, 2 # highest priority
bne x1, x2, fail

li x16, 0xe2201000
lw x1, 0x4(x16) # claim reg, ctx 1
li x2, 1 # lowest id
bne x1, x2, fail

li x16, 0xe2201000
li x1, 2 # complete without claim from ctx 1 - should reset int source gateway
sw x1, 0x4(x16)

li x16, 0xe2201000
lw x1, 0x4(x16) # claim reg, ctx 1
li x2, 2 # highest priority - from unlocked gateway
bne x1, x2, fail

li x16, 0xe2200000
lw x1, 0x4(x16) # claim reg, ctx 0
li x2, 3 # lowest id
bne x1, x2, fail

lw x1, 0x4(x16) # claim reg, ctx 0
li x2, 4 # lowest id
bne x1, x2, fail

li x16, 0xe2001000
lw x1, (x16)
bne x1, x0, fail  # no plic irqs pending

pass:
li x31, 0xcafe
1:
j 1b

fail:
j fail
