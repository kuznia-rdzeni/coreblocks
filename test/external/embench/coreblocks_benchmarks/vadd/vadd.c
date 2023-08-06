/* clang -DCPU_MHZ=0.01 -S vadd.c -I ../../embench-iot/support/ --target=riscv32 -march=rv32i_zve32x */
#include "support.h"

/* This scale factor will be changed to equalise the runtime of the
   benchmarks. */
#define LOCAL_SCALE_FACTOR 150

/* Some basic types.  */
typedef unsigned char BYTE;
typedef unsigned long DWORD;
typedef unsigned short WORD;

const DWORD LEN = 32;
const DWORD asm_start_counter = 10;
void init_tab(DWORD *tab)
{
  for(unsigned int i = 0; i < LEN; i++)
  {
    tab[i]=i;
  }
}

DWORD __attribute__((noinline)) vadd_body()
{
  DWORD tab[LEN];
  DWORD counter = asm_start_counter;
  init_tab(tab);
  asm volatile ("vsetvli x0, %[LEN], e32,m1,ta,ma \n"
                "vle32.v v1, (%[tab]) \n"
                "vadd.vi v2, v1, 0 \n"
                "start_vadd_%=: \n"
                "vadd.vv v2, v2, v1 \n"
                "addi %[counter], %[counter], -1 \n"
                "bne x0, %[counter], start_vadd_%= \n"
                "vse32.v v2, (%[tab])"
                : [counter]"+r"(counter)
                : [LEN]"r"(LEN),
                  [tab]"r"(tab)
                : "v1", "v2", "memory");
  DWORD result = 0;
  for(unsigned int i = 0; i < LEN; i++)
  {
    result += tab[i];
  }
  return result;
}


static int __attribute__ ((noinline)) benchmark_body (int rpt)
{
  int i;
  DWORD r;

  for (i = 0; i < rpt; i++)
  {
    r = vadd_body();
  }

  return (unsigned int) r;
}


void initialise_benchmark (void)
{ }

void warm_caches (int  heat)
{
  benchmark_body (heat);
  return;
}

int benchmark (void)
{
  return benchmark_body (LOCAL_SCALE_FACTOR * CPU_MHZ);
}


int verify_benchmark (int r)
{
  DWORD tab[LEN];
  init_tab(tab);
  int result =0;
  for (unsigned int i=0; i< LEN; i++)
  {
    result += tab[i]*(asm_start_counter +1);
  }

  return result == r;
}
