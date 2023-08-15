#include "support.h"

typedef unsigned long DWORD;
#define _LEN 32
const DWORD LEN = _LEN;
DWORD tab_in[_LEN];
DWORD tab_out[_LEN];
DWORD support_tab[_LEN];
const unsigned int body_iterations = 50;

DWORD __attribute__((noinline)) vadd_body(DWORD counter)
{
  asm volatile (
                "vsetvli x0, %[LEN], e32,m1,ta,ma \n"
                "start_vadd_%=: \n"
                "vle32.v v1, (%[tab_in]) \n"
                "vle32.v v2, (%[support_tab]) \n"
                "vadd.vv v2, v2, v1 \n"
                "vse32.v v2, (%[support_tab]) \n"
                "addi %[counter], %[counter], -1 \n"
                "bne x0, %[counter], start_vadd_%= \n"
                "vle32.v v2, (%[support_tab]) \n"
                "vse32.v v2, (%[tab_out]) \n"
                : [counter]"+r"(counter)
                : [LEN]"r"(LEN),
                  [tab_in]"r"(tab_in),
                  [tab_out]"r"(tab_out),
                  [support_tab] "r"(support_tab)
                : "v1", "v2", "v3", "memory");
  return 0;
}

void initialise_benchmark (void)
{
  for(unsigned int i = 0; i < LEN; i++)
  {
    tab_in[i]=i;
    support_tab[i] = 0;
  }
}

void warm_caches (int __attribute__((unused)) heat)
{
  vadd_body(4);
  initialise_benchmark();
  return;
}

int benchmark (void)
{
  return vadd_body(body_iterations);
}

int verify_benchmark (int __attribute__((unused)) r)
{
  int expected =0;
  int got = 0;
  for(unsigned int i = 0; i < LEN; i++)
  {
    got += tab_out[i];
    expected += tab_in[i]*body_iterations;
  }

//  asm volatile(
//  "li t0, 0x80000004 \n"
//  "sw %[out], 0(t0) \n"
//  "li t0, 0x80000000 \n"
//  "sw a0, 0(t0) \n"
//  :
//  : [out] "r"(r)
//  : "memory");
  return expected == got;
}
