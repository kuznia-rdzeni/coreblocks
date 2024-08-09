OUTPUT_ARCH( "riscv" )

start = 0;

SECTIONS
{
  .text : { *(.text) }
  . = 0x100000000; /* start from 2**32 - trick to emulate Harvard architecture (memory addresses will start from 0) */
  .data : {
      *(.data)
      *(.bss)

      . =  _end_init_regs > . ? 0x1000 : .;  /* skip .init_regs origin allocation if not used */
      *(.init_regs)
      _end_init_regs = .;
   }
}
