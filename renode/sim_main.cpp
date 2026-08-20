#include "sim_coreblocks.h"
#include "src/renode.h"
#include "src/peripherals/cpu-agent.h"
#include "src/buses/wishbone-initiator.h"

Coreblocks *core = nullptr;
CpuAgent *agent = nullptr;
vluint64_t main_time = 0;

void evaluateModel()
{
    core->evaluateModel();
}

RenodeAgent *Init()
{
    Verilated::commandArgs(0, (const char **)nullptr);

    WishboneInitiator<uint32_t, uint32_t> *instructionFetchBus = new WishboneInitiator<uint32_t, uint32_t>();
    WishboneInitiator<uint32_t, uint32_t> *loadStoreBus = new WishboneInitiator<uint32_t, uint32_t>();

    agent = new CpuAgent(instructionFetchBus);
    agent->addBus(loadStoreBus);

    core = new Coreblocks();

    core->setInstructionFetchBus(*instructionFetchBus);
    core->setLoadStoreBus(*loadStoreBus);

    agent->addCPU(core);

    instructionFetchBus->evaluateModel = evaluateModel;
    loadStoreBus->evaluateModel = evaluateModel;

    return agent;
}

int main(int argc, char **argv, char **env)
{
    if (argc < 3)
    {
        printf("Usage: %s {receiverPort} {senderPort} [{address}]\n", argv[0]);
        exit(-1);
    }
    const char *address = argc < 4 ? "127.0.0.1" : argv[3];

    Init();
    agent->simulate(atoi(argv[1]), atoi(argv[2]), address);

    return 0;
}

