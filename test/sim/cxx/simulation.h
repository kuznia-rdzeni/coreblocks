#pragma once

#include <pybind11/pybind11.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <string>

#include "memory.h"

class Vtop;
class VerilatedContext;

namespace cxxsim {

namespace py = pybind11;

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

    void add_ram(uint64_t start, uint64_t end, uint32_t flags, const py::bytes& initial_data);
    void add_mmio(uint64_t start, uint64_t end, uint32_t flags, py::object on_read, py::object on_write);

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
    bool has_run_ = false;
};

}  // namespace cxxsim
