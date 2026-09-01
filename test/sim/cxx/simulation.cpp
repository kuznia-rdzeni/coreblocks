#include "simulation.h"

#include <verilated.h>

#include <stdexcept>

#include "Vtop.h"
#include "wishbone.h"

namespace cxxsim {

namespace {

// Verilator escapes the double underscore of the Amaranth-generated port names
// (`wb_instr__cyc` becomes `wb_instr___05Fcyc`).
#define WB_PORT(top, bus, name) ((top).bus##___05F##name)

#define WB_SIGNALS(top, bus)                                                                  \
    WishboneSignals {                                                                         \
        &WB_PORT(top, bus, cyc), &WB_PORT(top, bus, stb), &WB_PORT(top, bus, we),             \
            &WB_PORT(top, bus, sel), &WB_PORT(top, bus, adr), &WB_PORT(top, bus, dat_w),      \
            &WB_PORT(top, bus, dat_r), &WB_PORT(top, bus, ack), &WB_PORT(top, bus, err),      \
            &WB_PORT(top, bus, rty)                                                           \
    }

}  // namespace

Simulation::Simulation(uint64_t timeout_cycles, bool fail_on_undefined_read, bool fail_on_undefined_write)
    : context_(std::make_unique<VerilatedContext>()),
      memory_(fail_on_undefined_read, fail_on_undefined_write),
      timeout_cycles_(timeout_cycles) {
    context_->traceEverOn(false);
    top_ = std::make_unique<Vtop>(context_.get(), "top");
}

Simulation::~Simulation() = default;

void Simulation::add_ram(uint64_t start, uint64_t end, uint32_t flags, const py::bytes& initial_data) {
    const std::string_view contents = std::string_view(initial_data);
    memory_.add_segment(std::make_unique<RamSegment>(
        start, end, flags, std::vector<uint8_t>(contents.begin(), contents.end())));
}

void Simulation::add_mmio(uint64_t start, uint64_t end, uint32_t flags, py::object on_read, py::object on_write) {
    memory_.add_segment(
        std::make_unique<CallbackSegment>(start, end, flags, std::move(on_read), std::move(on_write)));
}

RunResult Simulation::run() {
    if (has_run_) {
        throw std::runtime_error("A simulation can only be run once");
    }
    has_run_ = true;

    Vtop& top = *top_;

    WishboneSlave instr_bus(WB_SIGNALS(top, wb_instr), memory_, /*is_instr_bus=*/true);
    WishboneSlave data_bus(WB_SIGNALS(top, wb_data), memory_, /*is_instr_bus=*/false);

    top.interrupts = 0;

    auto cycle = [&]() {
        top.clk = 1;
        top.eval();

        instr_bus.on_falling_edge();
        data_bus.on_falling_edge();
        top.interrupts = interrupts_.load(std::memory_order_relaxed);

        top.clk = 0;
        top.eval();
    };

    // The callbacks take the GIL back for the duration of a call.
    py::gil_scoped_release gil;

    top.rst = 1;
    cycle();
    top.rst = 0;

    for (uint64_t i = 0; i < timeout_cycles_; i++) {
        cycle();

        if (stop_requested_.load(std::memory_order_relaxed)) {
            return RunResult{FinishReason::Stopped, i + 1};
        }
    }

    return RunResult{FinishReason::Timeout, timeout_cycles_};
}

}  // namespace cxxsim
