#include "sim_coreblocks.h"
#include "src/renode_bus.h"
#include "src/buses/wishbone-initiator.h"
#include "verilated_vcd_c.h"

Coreblocks::Coreblocks()
    : top()
{
    static uint8_t halted = 0;

    clockAndReset.clk_i = &top.clk;
    clockAndReset.rst_i = &top.rst;
    //clockAndReset.test_en_i = &top.test_en_i;
    //clockAndReset.scan_rst_ni = &top.scan_rst_ni;
    //clockAndReset.ram_cfg_i = &top.ram_cfg_i;
    clockAndReset.init();

    //configuration.boot_addr_i = &top.boot_addr_i;
    //configuration.hart_id_i = &top.hart_id_i;
    //configuration.init();

    //specialControlSignals.fetch_enable_i = &top.fetch_enable_i;
    specialControlSignals.core_sleep_o = &halted;
    //specialControlSignals.alert_minor_o = &top.alert_minor_o;
    //specialControlSignals.init();

    //interrupts.irq_nm_i = &top.irq_nm_i;
    //interrupts.irq_fast_i = &top.irq_fast_i;
    //interrupts.irq_external_i = &top.irq_external_i;
    //interrupts.irq_timer_i = &top.irq_timer_i;
    //interrupts.irq_software_i = &top.irq_software_i;

    //debug.debug_req_i = &top.debug_req_i;

#if VM_TRACE
    Verilated::traceEverOn(true);
    trace = new VerilatedVcdC;
    top.trace(trace, 99);  // Trace 99 levels of hierarchy (or see below)
    // tfp->dumpvars(1, "t");  // trace 1 level under "t"
    trace->open("/tmp/simx.vcd");  // beware: Renode manipulates CWD
#endif
    reset();
}

void Coreblocks::reset()
{
    *clockAndReset.rst_i = low;
    evaluateModel();
    *clockAndReset.rst_i = high;
    evaluateModel();
    *clockAndReset.rst_i = low;
    evaluateModel();
}

void Coreblocks::setInstructionFetchBus(CoreblocksBusInterface::Wishbone &wishbone)
{
    wishbone.wb_addr = &top.wb_instr___05Fadr;
    wishbone.wb_rd_dat = &top.wb_instr___05Fdat_r;
    wishbone.wb_wr_dat = &top.wb_instr___05Fdat_w;
    wishbone.wb_we = &top.wb_instr___05Fwe;
    wishbone.wb_sel = &top.wb_instr___05Fsel;
    wishbone.wb_stb = &top.wb_instr___05Fstb;
    wishbone.wb_ack = &top.wb_instr___05Fack;
    wishbone.wb_cyc = &top.wb_instr___05Fcyc;
    wishbone.wb_stall = &top.wb_instr___05Fstall;
    wishbone.wb_rst = &top.wb_instr___05Frst;
    wishbone.wb_clk = clockAndReset.clk_i;
}

void Coreblocks::setLoadStoreBus(CoreblocksBusInterface::Wishbone &wishbone)
{
    wishbone.wb_addr = &top.wb_data___05Fadr;
    wishbone.wb_rd_dat = &top.wb_data___05Fdat_r;
    wishbone.wb_wr_dat = &top.wb_data___05Fdat_w;
    wishbone.wb_we = &top.wb_data___05Fwe;
    wishbone.wb_sel = &top.wb_data___05Fsel;
    wishbone.wb_stb = &top.wb_data___05Fstb;
    wishbone.wb_ack = &top.wb_data___05Fack;
    wishbone.wb_cyc = &top.wb_data___05Fcyc;
    wishbone.wb_stall = &top.wb_data___05Fstall;
    wishbone.wb_rst = &top.wb_data___05Frst;
    wishbone.wb_clk = clockAndReset.clk_i;
}

void Coreblocks::evaluateModel()
{
    static int i = 0;
    // std::cerr << *this << "addr: " << top.wb_instr___05Fadr << "\ninterrupts: " << top.interrupts << '\n';
#if VM_TRACE
    trace->dump(i++);
#endif
    top.eval();
#if VM_TRACE
    trace->dump(i++);
#endif
}

void Coreblocks::onGPIO(int number, bool value)
{
    switch (number)
    {
    case 3:
        *interrupts.irq_software_i = value;
        break;
    case 7:
        *interrupts.irq_timer_i = value;
        break;
    case 11:
        *interrupts.irq_external_i = value;
        break;
    case 31:
        *interrupts.irq_nm_i = value;
        break;

    default:
        if (number >= 16 && number <= 30)
        {
            if (value)
                *interrupts.irq_fast_i |= (1U << (number - 16));
            else
                *interrupts.irq_fast_i &= ~(1U << (number - 16));
        }
        break;
    }
}

void Coreblocks::debugRequest(bool value)
{
    //*debug.debug_req_i = value;
}

DebuggableCPU::DebugProgram Coreblocks::getRegisterGetProgram(uint64_t id)
{
    DebugProgram debugProgram;
    debugProgram.address = debugProgramAddress;

    if (id < 32) // register
    {
        debugProgram.memory = {
            sw(id, 0, 0), // store x1 to memory
            dret};        // return
    }
    else //CSR
    {
        if (id == 32)   // if PC
            id = dpc; // DPC

        debugProgram.memory = {
            csrrw(0, dscratch0, 1), // move x1 to dscratch0
            csrrs(1, id, 0),        // move selected csr to x1
            sw(1, 0, 0),            // store x1 to memory
            csrrs(1, dscratch0, 0), //restore x1
            dret};                  // return
    }
    debugProgram.readCount = debugProgram.memory.size();
    return debugProgram;
}

DebuggableCPU::DebugProgram Coreblocks::getRegisterSetProgram(uint64_t id, uint64_t value)
{
    DebugProgram debugProgram;
    debugProgram.address = debugProgramAddress;

    if (id < 32) // register
    {
        uint32_t luiPart = value >> 12;
        uint32_t addiPart = value & 0xfff;
        if (addiPart & (1 << 11)) // addi appends negative numbers with ones
            luiPart += 1;         // if we add 1 to lui part all those ones overflow and dissapear

        debugProgram.memory = {
            lui(id, luiPart),       // upper 20 bits
            addi(id, id, addiPart), // lower 12 bits
            dret};                  // return
    }
    else //CSR
    {
        if (id == 32)   // if PC
            id = 0x7B1; // DPC

        uint32_t luiPart = value >> 12;
        uint32_t addiPart = value & 0xfff;
        if (addiPart & (1 << 11))
            luiPart += 1;

        debugProgram.memory = {
            csrrw(0, dscratch0, 1), // move x1 to dscratch0
            lui(1, luiPart),        // write value to x1
            addi(1, 1, addiPart),
            csrrw(0, id, 1),        // move x1 to selected csr
            csrrs(1, dscratch0, 0), //restore x1
            dret};                  // return
    }
    debugProgram.readCount = debugProgram.memory.size();
    return debugProgram;
}

DebuggableCPU::DebugProgram Coreblocks::getEnterSingleStepModeProgram()
{
    DebugProgram debugProgram;
    debugProgram.address = debugProgramAddress;
    debugProgram.memory = {
        csrrsi(0, dcsr, 1 << 2), // set dcsr.step
        dret};                   // return
    debugProgram.readCount = debugProgram.memory.size();
    return debugProgram;
}

DebuggableCPU::DebugProgram Coreblocks::getExitSingleStepModeProgram()
{
    DebugProgram debugProgram;
    debugProgram.address = debugProgramAddress;
    debugProgram.memory = {
        csrrci(0, dcsr, 1 << 2), // clear dcsr.step
        dret};                   // return
    debugProgram.readCount = debugProgram.memory.size();
    return debugProgram;
}
DebuggableCPU::DebugProgram Coreblocks::getSingleStepModeProgram()
{
    DebugProgram debugProgram;
    debugProgram.address = debugProgramAddress;
    debugProgram.memory = {
        dret}; // return
    debugProgram.readCount = debugProgram.memory.size();
    return debugProgram;
}

#define printPointerValueToStream(obj, ptr) stream << #ptr ": " << uint64_t(*obj.ptr) << '\n'

std::ostream &operator<<(std::ostream &stream, const ClockAndReset &clockAndReset)
{
    printPointerValueToStream(clockAndReset, clk_i);
    printPointerValueToStream(clockAndReset, rst_i);
    /*
    printPointerValueToStream(clockAndReset, test_en_i);
    printPointerValueToStream(clockAndReset, scan_rst_ni);
    printPointerValueToStream(clockAndReset, ram_cfg_i);
    */
    return stream;
}

std::ostream &operator<<(std::ostream &stream, const Configuration &configuration)
{
    /*
    printPointerValueToStream(configuration, hart_id_i);
    printPointerValueToStream(configuration, boot_addr_i);
    */
    return stream;
}

/*
std::ostream &operator<<(std::ostream &stream, const InstructionFetch &instructionFetch)
{
    printPointerValueToStream(instructionFetch, instr_req_o);
    printPointerValueToStream(instructionFetch, instr_addr_o);
    printPointerValueToStream(instructionFetch, instr_gnt_i);
    printPointerValueToStream(instructionFetch, instr_rvalid_i);
    printPointerValueToStream(instructionFetch, instr_rdata_i);
    printPointerValueToStream(instructionFetch, instr_err_i);
    return stream;
}

std::ostream &operator<<(std::ostream &stream, const LoadStore &loadStore)
{
    printPointerValueToStream(loadStore, data_req_o);
    printPointerValueToStream(loadStore, data_addr_o);
    printPointerValueToStream(loadStore, data_we_o);
    printPointerValueToStream(loadStore, data_be_o);
    printPointerValueToStream(loadStore, data_wdata_o);
    printPointerValueToStream(loadStore, data_gnt_i);
    printPointerValueToStream(loadStore, data_rvalid_i);
    printPointerValueToStream(loadStore, data_err_i);
    printPointerValueToStream(loadStore, data_rdata_i);
    return stream;
}
*/

std::ostream &operator<<(std::ostream &stream, const SpecialControlSignals &specialControlSignals)
{
    /*
    printPointerValueToStream(specialControlSignals, fetch_enable_i);
    printPointerValueToStream(specialControlSignals, alert_minor_o);
    printPointerValueToStream(specialControlSignals, alert_major_o);
    */
    printPointerValueToStream(specialControlSignals, core_sleep_o);
    return stream;
}

std::ostream &operator<<(std::ostream &stream, const Interrupts &interrupts)
{
    /*
    printPointerValueToStream(interrupts, irq_nm_i);
    printPointerValueToStream(interrupts, irq_fast_i);
    printPointerValueToStream(interrupts, irq_external_i);
    printPointerValueToStream(interrupts, irq_timer_i);
    printPointerValueToStream(interrupts, irq_software_i);
    */
    return stream;
}

std::ostream &operator<<(std::ostream &stream, const Debug &debug)
{
    /*
    printPointerValueToStream(debug, debug_req_i);
    */
    return stream;
}

std::ostream &operator<<(std::ostream &stream, const Coreblocks &core)
{
    stream << core.clockAndReset << core.configuration /*<< core.instructionFetch << core.loadStore*/ << core.specialControlSignals << core.debug;
    return stream;
}

