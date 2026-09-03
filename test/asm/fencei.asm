  .insn 0x0000108f # fence.i with nonzero rd
  lw x1, 0(x0)
  csrw 0x8fe, 0x10
