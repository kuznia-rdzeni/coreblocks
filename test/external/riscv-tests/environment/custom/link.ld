OUTPUT_ARCH( "riscv" )
ENTRY(_start)

MEMORY
{
    text (rxai!w) : ORIGIN = 0x80000000, LENGTH = 64K
    data (wxa!ri) : ORIGIN = 0x90000000, LENGTH = 128K
}

SECTIONS
{
  .text.init : { *(.text.init) } >text
  .text : { *(.text .text.*) . = ALIGN(0x40); } >text
  .data : { *(.data .data.*) } >data
  .bss : { *(.bss .bss.*) . = ALIGN(0x40); } >data
  _end = .;
}
