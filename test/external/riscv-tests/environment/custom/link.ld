OUTPUT_ARCH( "riscv" )
ENTRY(_start)

MEMORY
{
    text (rxai!w) : ORIGIN = 0x00000000, LENGTH = 64K
    data (wxa!ri) : ORIGIN = 0x10000000, LENGTH = 128K
}

PHDRS
{
  text PT_LOAD;
  data_init PT_LOAD;
  data PT_NULL;
}

SECTIONS
{
  .text.init : { *(.text.init) } >text AT>text :text
  . = ALIGN(0x1000);
  .text : { *(.text) } >text AT>text :text
  . = ALIGN(0x1000);
  .data : { *(.data) } >data AT>data :data_init
  .bss : { *(.bss) } >data AT>data :data
  _end = .;
}

