#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <string_view>

#include "memory.h"

class Vtop;
class VerilatedContext;

namespace cxxsim {

enum class FinishReason {
    // Python asked us to stop
    Stopped = 0,
    Timeout = 1,
};

struct RunResult {
    FinishReason reason;
    uint64_t cycles;
};

class Simulation {
  public:
    Simulation(uint64_t timeout_cycles, bool fail_on_undefined_read, bool fail_on_undefined_write);
    ~Simulation();

    Simulation(const Simulation&) = delete;
    Simulation& operator=(const Simulation&) = delete;

    void add_ram(address_t start, address_t end, uint32_t flags, std::string_view initial_data);
    void add_mmio(address_t start, address_t end, uint32_t flags, read_callback_t on_read,
                  write_callback_t on_write);

    void request_stop() { stop_requested_ = true; }
    void set_interrupts(uint32_t interrupts) { interrupts_ = interrupts; }

    RunResult run();

  private:
    void cycle();

    std::unique_ptr<VerilatedContext> context_;
    std::unique_ptr<Vtop> top_;
    MemoryMap memory_;

    uint64_t timeout_cycles_;
    std::atomic<bool> stop_requested_{false};
    std::atomic<uint32_t> interrupts_{0};
    std::atomic<bool> has_run_{false};
};

}  // namespace cxxsim
