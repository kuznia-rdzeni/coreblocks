#include <support.h>
#include <stdint.h>
#include <stdlib.h>

#define read_csr(reg) ({ unsigned long __tmp; \
  asm volatile ("csrr %0, " #reg : "=r"(__tmp)); \
  __tmp; })

#define rdinstret() ((((uint64_t) read_csr(instreth)) << 32) | read_csr(instret))

uint64_t rdcycle()
{
  uint32_t low = read_csr(cycle);
  uint64_t high = read_csr(cycleh);
  return (high << 32) | low;
}

typedef struct {
    uint64_t cycle_cnt;
    uint64_t instr_cnt;
} to_host;

#define TO_HOST (*((volatile to_host*) (0x80000008UL)))

static uint64_t cycle_cnt_start;
static uint64_t instr_cnt_start;

inline void start_trigger() {
    instr_cnt_start = rdinstret();
    asm volatile ("":::"memory");
    cycle_cnt_start = rdcycle();
}

inline void stop_trigger() {
    uint64_t cycle_cnt_end = rdcycle();
    asm volatile ("":::"memory");
    uint64_t instr_cnt_end = rdinstret();
    TO_HOST.cycle_cnt = cycle_cnt_end - cycle_cnt_start;
    TO_HOST.instr_cnt = instr_cnt_end - instr_cnt_start;
}

void initialise_board () {
}
