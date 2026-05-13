# PLIC test, writes to CSR set PLIC interrupt input
# context 0 - MEI, context 1 - SEI

# plic base
li x16, 0xE2000000

# trigger interrupt
csrwi 0x7ff, 0b010

lw x1, 0x1000(x16)
li x2, 0b10 # irq 1 pending
bne x1, x2, fail

li x1, 0x200004(x16) # claim reg ctx 0
bne x1, x0, fail

# plic enable bit for irq 1, ctx 0
li x1, 0b10
sw x1, 0x2000(x16)

li x1, 0x200004(x16) # claim reg ctx 0
bne x1, x0, fail

lw x1, 0x1000(x16)
li x2, 0b10 # plic irq 1 pending
bne x1, x2, fail

# set positive int 1 priority
li x1, 1
sw x1, 0x4(x16)

lw x1, 0x200004(x16) # claim reg, ctx 0
li x2, 1 # claim irq 1 successful
bne x1, x2, fail

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

lw x1, 0x200004(x16) # claim for ctx 1 should fail
bne x1, x0, fail

li x1, 2 # complete some other id
sw x1, 0x200004(x16) # complete reg, ctx 0

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

li x1, 1 # complete irq 1
sw x1, 0x20004(x16) # complete reg, ctx 0
bne x1, x2, fail

lw x1, 0x1000(x16)
li x2, 0b10 # should be pending again because external signal still high
bne x1, x2, fail

csrr x1, mip
li x2, 1 << 11
bne x1, x2, fail # MEI should be pending

# increase context 0 priority treshold
li x1, 1
sw x1, 0x200000(x16)

csrr x1, mip
bne x1, x0, fail # no interrupts pending

lw x1, 0x201004(x16) # claim for ctx 1 should fail
bne x1, x0, fail

# plic enable bit for irq 1, ctx 1
li x1, 0b10
sw x1, 0x2000(x16)

csrr x1, mip
li x2, 1 << 9
bne x1, x2, fail # SEI should be pending

lw x1, 0x200004(x16) # claim for ctx 0 should fail
bne x1, x0, fail

lw x1, 0x201004(x16) # claim reg, ctx 1
li x2, 1 # claim irq 1 successful
bne x1, x2, fail

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

# plic disable bit for irq 1, ctx 0
li x1, 0b10
sw x1, 0x0000(x16)

# completion from disabled id should be ignored
li x1, 1
sw x1, 0x200004(x16) # complete reg, ctx 0

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

li x1, 1
sw x1, 0x201004(x16) # complete reg, ctx 1

lw x1, 0x1000(x16)
li x2, 0b10 # plic irq 1 pending
bne x1, x2, fail

csrw 0x7ff, x0 # disable interrupt source

li x1, 1
sw x1, 0x201004(x16) # complete without claim from ctx 1

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

csrr x1, mip
bne x1, x0, fail # no interrupts pending

li x1, 0b11110
csrw 0x7ff, x1 # enable interrupt sources

# set enables
sw x1, 0x2000(x16) # enables ctx0
sw x1, 0x2080(x16) # enables ctx1

# reset context 0 priority treshold
sw x0, 0x200000(x16)

# set higher int 2 priority
li x1, 2
sw x1, 0x8(x16)

# set int 3 priority same as int 1
li x1, 1
sw x1, 0xc(x16)

lw x1, 0x200004(x16) # claim reg, ctx 0
li x2, 2 # highest priority
bne x1, x2, fail

lw x1, 0x201004(x16) # claim reg, ctx 1
li x2, 1 # lowest id
bne x1, x2, fail

lw x1, 0x200004(x16) # claim reg, ctx 0
li x2, 3 # lowest id
bne x1, x2, fail

lw x1, 0x200004(x16) # claim reg, ctx 0
li x2, 4 # lowest id
bne x1, x2, fail

lw x1, 0x1000(x16)
bne x1, x0, fail  # no plic irqs pending

pass:
li x31, 0xcafe
j pass

fail:
j fail

