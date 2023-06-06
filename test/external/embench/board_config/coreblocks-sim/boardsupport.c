#include <support.h>
#include <stdint.h>
#include <stdlib.h>

#define read_csr(reg) ({ unsigned long __tmp; \
  asm volatile ("csrr %0, " #reg : "=r"(__tmp)); \
  __tmp; })

#define rdcycle() ((((uint64_t) read_csr(cycleh)) << 32) | read_csr(cycle))
#define rdinstret() ((((uint64_t) read_csr(instreth)) << 32) | read_csr(instret))

typedef struct {
    uint64_t cycle_cnt;
    uint64_t instr_cnt;
} to_host;

#define TO_HOST (*((volatile to_host*) (0x80000008UL)))

static uint64_t cycle_cnt_start;
static uint64_t instr_cnt_start;

void start_trigger() {
    cycle_cnt_start = rdcycle();
    instr_cnt_start = rdinstret();
}

void stop_trigger() {
    TO_HOST.cycle_cnt = rdcycle() - cycle_cnt_start;
    TO_HOST.instr_cnt = rdinstret() - instr_cnt_start;
}

void initialise_board () {
}
