_start:
	li x31, 0xde

	la x1, machine_trap
	csrw mtvec, x1

	la x1, supervisor_trap
	csrw stvec, x1

	# Delegate ILLEGAL_INSTRUCTION to supervisor handler for lower-privilege origins.
	li x1, 1 << 2
	csrw medeleg, x1

m_illegal_site:
	# Same exception cause as below, but from M-mode: must stay in M-mode.
	.4byte 0

after_m_illegal:
	li x5, 1

	# Enter supervisor mode via MRET.
	li x1, 0b11 << 11
	csrc mstatus, x1
	li x1, 0b01 << 11
	csrs mstatus, x1

	la x1, s_mode_main
	csrw mepc, x1
	mret

s_mode_main:
	# Same exception cause as above, now from S-mode: should be delegated to S-mode trap.
s_illegal_site:
	.4byte 0

after_s_illegal:
	li x4, 1
	li x6, 1
	bne x7, x6, fail
	j pass

supervisor_trap:
	csrr x8, scause
	li x9, 2 # ILLEGAL_INSTRUCTION
	bne x8, x9, fail

	csrr x10, sepc
	la x11, s_illegal_site
	bne x10, x11, fail

	li x7, 1

	addi x10, x10, 4
	csrw sepc, x10
	sret

machine_trap:
	csrr x10, mcause
	li x11, 2 # ILLEGAL_INSTRUCTION
	bne x10, x11, fail

	csrr x12, mepc
	la x13, m_illegal_site
	bne x12, x13, fail

	addi x12, x12, 4
	csrw mepc, x12
	mret

fail:
	j fail

pass:
	j pass
