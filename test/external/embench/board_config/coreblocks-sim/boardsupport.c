#include <support.h>
#include <stdint.h>
#include <stdlib.h>

#define read_csr(reg) ({ unsigned long __tmp; \
  asm volatile ("csrr %0, " #reg : "=r"(__tmp)); \
  __tmp; })

#define read_csr64(high, low) ((((uint64_t) read_csr(high)) << 32) | read_csr(low))

#define rdcycle() read_csr64(cycleh, cycle)
#define rdinstret() read_csr64(instreth, instret)
// mhpmcounter3h:mhpmcounter3, programmed in initialise_board to count branch mispredictions
#define rdmispredict() read_csr64(0xb83, 0xb03)

typedef struct {
    uint64_t cycle_cnt;
    uint64_t instr_cnt;
    uint64_t mispredict_cnt;
} to_host;

#define TO_HOST (*((volatile to_host*) (0x80000010UL)))

static to_host start;

static to_host read_counters() {
    return (to_host) {
        .cycle_cnt = rdcycle(),
        .instr_cnt = rdinstret(),
        .mispredict_cnt = rdmispredict(),
    };
}

void start_trigger() {
    start = read_counters();
}

void stop_trigger() {
    to_host end = read_counters();
    TO_HOST.cycle_cnt = end.cycle_cnt - start.cycle_cnt;
    TO_HOST.instr_cnt = end.instr_cnt - start.instr_cnt;
    TO_HOST.mispredict_cnt = end.mispredict_cnt - start.mispredict_cnt;
}

void initialise_board () {
    // csrwi mhpmevent3, HPMEvent.BRANCH_MISPREDICTION
    asm volatile ("csrwi 0x323, 1");
}
