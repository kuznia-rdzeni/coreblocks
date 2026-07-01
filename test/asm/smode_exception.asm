_start:
	li x5, 0
	li x6, 0
	li x7, 0
	li x8, 0

	# Configure PMP: allow all access for S-mode
	li x1, 0x1F
	csrw pmpcfg0, x1
	li x1, -1
	csrw pmpaddr0, x1

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
	addi x5, x5, 1

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
	addi x6, x6, 1
	j pass

supervisor_trap:
	addi x7, x7, 1

	csrr x1, scause
	li x2, 2 # ILLEGAL_INSTRUCTION
	bne x1, x2, fail

	csrr x1, sepc
	la x2, s_illegal_site
	bne x1, x2, fail

	addi x1, x1, 4
	csrw sepc, x1

	sret

machine_trap:
	addi x8, x8, 1

	csrr x1, mcause
	li x2, 2 # ILLEGAL_INSTRUCTION
	bne x1, x2, fail

	csrr x1, mepc
	la x2, m_illegal_site
	bne x1, x2, fail

	addi x1, x1, 4
	csrw mepc, x1
	mret

fail:
	j fail

pass:
	j pass
