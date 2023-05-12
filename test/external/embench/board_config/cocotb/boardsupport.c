#include <support.h>
#include <stdint.h>
#include <stdlib.h>

__attribute__((section(".tohost")))
volatile static struct {
    uint32_t finished;
    uint64_t cycle_cnt;
    uint64_t instr_cnt;
} to_host;

void start_trigger() {

}

void stop_trigger()
{
    to_host.finished = 2137;
}

void
initialise_board ()
{
}