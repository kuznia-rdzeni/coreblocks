start:
  la x5, trap
  csrw mtvec, x5

  li x1, 1
  slli x2, x1, 2
  andi x3, x2, 0x4
  bnez x3, continue

  nop

continue:
  lw x4, 0(x0)
  unimp

  nop

.p2align 2
trap:
  j .

.section .data
.word 0xDEADBEEF
