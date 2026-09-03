  li x12, 0x00950513  # addi x10, x10, 9
  sw x12, (4 * 3)(x0)
  .insn 0x0000108f # fence.i with nonzero rd
selfmodify_1:
  addi x10, x10, 1 # original code
  # x10 = 3 + 9

  lw x1, 0(x0)
  csrw 0x8fe, 0x10
