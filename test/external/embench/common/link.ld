OUTPUT_ARCH( "riscv" )
ENTRY(_start)

_STACK_SIZE = 0x1000;

MEMORY
{
    imem (rxai!w) : ORIGIN = 0x80000000, LENGTH = 64K
    dmem (wxa!ri) : ORIGIN = 0x90000000, LENGTH = 128K
}

SECTIONS
{
  .text.init : {
    *(.text.init)
  } >imem

  .text : {
    *(.text .text.*)
    . = ALIGN(0x40);
  } >imem

  .rodata : {
    *(.rodata .rodata.*)
    . = ALIGN(0x40);
  } >dmem

  .data :
  {
    . = ALIGN(4);

    *(.data .data.* .gnu.linkonce.d.*)

    . = ALIGN(8);
    __global_pointer$ = . + 0x800;

    *(.srodata.cst16) *(.srodata.cst8) *(.srodata.cst4) *(.srodata.cst2) *(.srodata .srodata.*)
    *(.sdata .sdata.* .gnu.linkonce.s.*)

    . = ALIGN(4);
  } >dmem

  .bss :
  {
    . = ALIGN(4);
    __bss_start = .;

    *(.dynbss)
    *(.bss .bss.* .gnu.linkonce.b.*)
    *(.dynsbss)
    *(.sbss .sbss.* .gnu.linkonce.sb.*)
    *(.scommon)

    . = ALIGN(4);
    __bss_end = .;
  } >dmem

  .stack : {
    __stack_end = .;
    . += _STACK_SIZE;
    . = ALIGN(0x40);
    __stack_top = .;
  } >dmem

  _end = .;
}
