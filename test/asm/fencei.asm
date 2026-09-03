# Testcase: fence.i with nonzero rd
  li x10, 3
  la x13, insn1
  lw x12, 0(x13)
  la x14, selfmodify_1
  sw x12, 0(x14)
Zifencei_fence_i_cg_cp_custom_fencei_fence_i_with_nonzero_rd:
  .insn 0x0000108f # fence.i with nonzero rd
selfmodify_1:
  addi x10, x10, 1 # original code
  # x10 = 3 + 9

# Testcase: fence.i with nonzero funct12
  li x16, 3
  la x13, insn2
  lw x1, 0(x13)
  la x14, selfmodify_2
  sw x1, 0(x14)
Zifencei_fence_i_cg_cp_custom_fencei_fence_i_with_nonzero_funct12:
  .insn 0x0010100f # fence.i with nonzero funct12
selfmodify_2:
  addi x16, x16, 1 # original code
  # x16 = 3 + 13

pass:
csrw 0x8fe, 0x10
j pass

insn1: addi x10, x10, 9
insn2: addi x16, x16, 13
