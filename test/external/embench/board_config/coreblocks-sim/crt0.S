.section ".text.init"
.globl _start
_start:

.init_xreg:
  li  x1, 0
  li  x2, 0
  li  x3, 0
  li  x4, 0
  li  x5, 0
  li  x6, 0
  li  x7, 0
  li  x8, 0
  li  x9, 0
  li  x10,0
  li  x11,0
  li  x12,0
  li  x13,0
  li  x14,0
  li  x15,0
  li  x16,0
  li  x17,0
  li  x18,0
  li  x19,0
  li  x20,0
  li  x21,0
  li  x22,0
  li  x23,0
  li  x24,0
  li  x25,0
  li  x26,0
  li  x27,0
  li  x28,0
  li  x29,0
  li  x30,0
  li  x31,0

.option push
.option norelax
  la gp, __global_pointer$
.option pop

.init_bss:
  la a0, __bss_start
  la a1, __bss_end-4 // section end is actually the start of the next section
  li a2, 0x0
  jal _fill_block

.init_stack:
  la  sp, __stack_top

  // argc, argv, envp is 0
  li a0, 0
  li a1, 0
  li a2, 0

  jal main

.inf_loop:
  // Store the return code
  li t0, 0x80000004
  sw a0, 0(t0);
  // Signal that we finished the test
  li t0, 0x80000000
  sw a0, 0(t0);
  j .inf_loop

/* Fills memory blocks */
_fill_block:
    sw a2, 0(a0)
    bgeu a0, a1, .fb_end
    addi a0, a0, 4
    j _fill_block
.fb_end:
    ret