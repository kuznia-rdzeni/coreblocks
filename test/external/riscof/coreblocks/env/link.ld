OUTPUT_ARCH( "riscv" )
ENTRY(rvtest_entry_point)

MEMORY
{
    text (rxai!w) : ORIGIN = 0x00000000, LENGTH = 2M
    data (wxa!ri) : ORIGIN = 0x10000000, LENGTH = 1M
    mmio (wa!rxi) : ORIGIN = 0x80000000, LENGTH = 1K
    signature (wa!rxi) : ORIGIN = 0x81000000, LENGTH = 16K

}

PHDRS
{
    text PT_LOAD;
    data_init PT_LOAD;
    data PT_NULL;
    mmio PT_LOAD;
    signature PT_LOAD;
}

SECTIONS
{
  .text.init : { *(.text.init) } >text AT>text :text
  . = ALIGN(0x1000);
  .text : { *(.text) } >text AT>text :text

  . = ALIGN(0x1000);
  .data : { *(.data) } >data AT>data :data_init
  .data.string : { *(.data.string)} >data AT>data :data_init
  .bss : { *(.bss) } >data AT>data :data

  . = ALIGN(0x1000);
  .hostmmio : { *(.hostmmio) } >mmio AT>mmio :mmio

  . = ALIGN(0x1000);
  .signature : { *(.signature) } >signature AT>signature :signature

  _end = .;
}
