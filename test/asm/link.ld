OUTPUT_ARCH( "riscv" )

start = 0;

SECTIONS
{
  .text : { *(.text) }
  . = 0x100000000; /* start from 2**32 - trick to emulate Harvard architecture (.bss addresses will start from 0) */
  .bss : { *(.bss) }
  _end = .;
}
