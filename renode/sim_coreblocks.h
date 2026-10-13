#ifndef SIM_IBEX_H
#define SIM_IBEX_H

#include <ostream>
#include "Vcore.h"
#include "verilated.h"
#include "riscv-instructions.h"
#include "src/peripherals/cpu-interface.h"

constexpr uint32_t high = 1;
constexpr uint32_t low = 0;

template <typename data_t, typename addr_t>
struct WishboneInitiator;
struct CoreblocksBusInterface
{
    using Wishbone = WishboneInitiator<uint32_t, uint32_t>;
};

struct ClockAndReset
{
    uint8_t *clk_i;
    uint8_t *rst_i;
    uint8_t *test_en_i;
    uint8_t *scan_rst_ni;
    uint16_t *ram_cfg_i; // 10 bit

    void init()
    {
        *clk_i = low;
        *rst_i = low;
        //*test_en_i = low;
        //*scan_rst_ni = high;
        //*ram_cfg_i = low;
    }

    void clockHigh()
    {
        *clk_i = high;
    }

    void clockLow()
    {
        *clk_i = low;
    }
};

struct Configuration
{
    uint32_t *hart_id_i;
    uint32_t *boot_addr_i;

    void init()
    {
        *hart_id_i = low;
        *boot_addr_i = low;
    }
};

struct SpecialControlSignals
{
    uint8_t *fetch_enable_i;
    uint8_t *alert_minor_o;
    uint8_t *alert_major_o;
    uint8_t *core_sleep_o;

    void init()
    {
        *fetch_enable_i = high;
    }
};

struct Interrupts
{
    uint8_t *irq_nm_i;
    uint16_t *irq_fast_i;
    uint8_t *irq_external_i;
    uint8_t *irq_timer_i;
    uint8_t *irq_software_i;
};

struct Debug
{
    uint8_t *debug_req_i;
};

class Coreblocks : public DebuggableCPU, protected RiscVInstructions
{
public:
    Coreblocks();

    void reset() override;
    void setInstructionFetchBus(CoreblocksBusInterface::Wishbone &wishbone);
    void setLoadStoreBus(CoreblocksBusInterface::Wishbone &wishbone);

    void onGPIO(int number, bool value) override;
    bool isHalted() override { return *specialControlSignals.core_sleep_o; }
    void clkHigh() override { *clockAndReset.clk_i = high; }
    void clkLow() override { *clockAndReset.clk_i = low; }
    void evaluateModel() override;
    void debugRequest(bool value) override;
    DebugProgram getRegisterGetProgram(uint64_t id) override;
    DebugProgram getRegisterSetProgram(uint64_t id, uint64_t value) override;
    DebugProgram getEnterSingleStepModeProgram() override;
    DebugProgram getExitSingleStepModeProgram() override;
    DebugProgram getSingleStepModeProgram() override;

private:
    uint32_t end(bool jumpToBegin, int offsetToBegin) { return jumpToBegin ? jal(0, (-offsetToBegin + 1) * 4) : dret; }

    Vcore top;
    VerilatedVcdC* trace;

    ClockAndReset clockAndReset;
    Configuration configuration;
    //InstructionFetch instructionFetch;
    //LoadStore loadStore;
    SpecialControlSignals specialControlSignals;
    Interrupts interrupts;
    Debug debug;

    static constexpr uint32_t debugProgramAddress = 0x1A110800;
    static constexpr uint32_t dscratch0 = 0x7b2;
    static constexpr uint32_t dpc = 0x7B1;
    static constexpr uint32_t dcsr = 0x7B0;

    friend std::ostream &operator<<(std::ostream &stream, const Coreblocks &core);
};

std::ostream &operator<<(std::ostream &stream, const ClockAndReset &clockAndReset);
std::ostream &operator<<(std::ostream &stream, const Configuration &configuration);
//std::ostream &operator<<(std::ostream &stream, const InstructionFetch &instructionFetch);
//std::ostream &operator<<(std::ostream &stream, const LoadStore &loadStore);
std::ostream &operator<<(std::ostream &stream, const SpecialControlSignals &specialControlSignals);
std::ostream &operator<<(std::ostream &stream, const Interrupts &interrupts);
std::ostream &operator<<(std::ostream &stream, const Coreblocks &core);

#endif /* SIM_IBEX_H */

