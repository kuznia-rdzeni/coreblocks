#include "support.h"

typedef unsigned long DWORD;
const DWORD LEN = 32;
const DWORD asm_start_counter = 1;
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
  DWORD support_tab[LEN];
  DWORD counter = asm_start_counter;
  init_tab(tab);
  for(unsigned int i=0; i<LEN; i++)
  {
    support_tab[i]=0;
  }
  asm volatile (
                "addi x0, x0, 0 \n"
                "vsetvli x0, %[LEN], e32,m1,ta,ma \n"
                "start_vadd_%=: \n"
                "vle32.v v1, (%[tab]) \n"
                "vle32.v v2, (%[support_tab]) \n"
                "vadd.vv v2, v2, v1 \n"
                "vse32.v v2, (%[support_tab]) \n"
                "addi %[counter], %[counter], -1 \n"
                "bne x0, %[counter], start_vadd_%= \n"
                "vle32.v v2, (%[support_tab]) \n"
                "vse32.v v2, (%[tab]) \n"
                : [counter]"+r"(counter)
                : [LEN]"r"(LEN),
                  [tab]"r"(tab),
                  [support_tab] "r"(support_tab)
                : "v1", "v2", "v3", "memory");
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

void warm_caches (int __attribute__((unused)) heat)
{
  benchmark_body (1);
  return;
}

int benchmark (void)
{
  return benchmark_body(5);
}

int verify_benchmark (int r)
{
  DWORD tab[LEN];
  init_tab(tab);
  int result =0;
  for (unsigned int i=0; i< LEN; i++)
  {
    result += tab[i]*asm_start_counter;
  }

  return result == r;
}


