#pragma once

#include <cstdint>

#include "memory.h"

namespace cxxsim {

// The names are the Wishbone ones, from the point of view of the master - the core.
struct WishboneSignals {
    // Driven by the core.
    const uint8_t* cyc;
    const uint8_t* stb;
    const uint8_t* we;
    const uint8_t* sel;
    const uint32_t* adr;
    const uint32_t* dat_w;

    // Driven by us.
    uint32_t* dat_r;
    uint8_t* ack;
    uint8_t* err;
    uint8_t* rty;
};

class WishboneSlave {
  public:
    WishboneSlave(WishboneSignals signals, MemoryMap& memory, bool is_instr_bus, unsigned delay = 0);

    void on_falling_edge();

  private:
    struct Reply {
        ReplyStatus status = ReplyStatus::Ok;
        uint32_t data = 0;
    };

    Reply handle_request();
    void drive(const Reply& reply);
    void drive_idle();

    static constexpr uint8_t WORD_BYTES = 4;
    static constexpr unsigned ADDR_SHIFT = 2;

    WishboneSignals signals_;
    MemoryMap& memory_;
    bool is_instr_bus_;
    unsigned delay_;

    Reply pending_;
    unsigned delay_left_ = 0;
    bool responding_ = false;
};

}  // namespace cxxsim
