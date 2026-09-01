#include "wishbone.h"

#include <stdexcept>

namespace cxxsim {

WishboneSlave::WishboneSlave(WishboneSignals signals, MemoryMap& memory, bool is_instr_bus, unsigned delay)
    : signals_(signals), memory_(memory), is_instr_bus_(is_instr_bus), delay_(delay) {
    drive_idle();
}

void WishboneSlave::drive_idle() {
    *signals_.dat_r = 0;
    *signals_.ack = 0;
    *signals_.err = 0;
    *signals_.rty = 0;
}

void WishboneSlave::drive(const Reply& reply) {
    *signals_.dat_r = reply.data;
    *signals_.ack = reply.status == ReplyStatus::Ok;
    *signals_.err = reply.status == ReplyStatus::Error;
    *signals_.rty = reply.status == ReplyStatus::Retry;
}

WishboneSlave::Reply WishboneSlave::handle_request() {
    // Wishbone addresses words, so the address has to be shifted to get a byte address.
    uint32_t addr = *signals_.adr << ADDR_SHIFT;
    uint8_t sel = *signals_.sel;

    Reply reply;
    if (*signals_.we) {
        reply.status = memory_.write(addr, *signals_.dat_w, WORD_BYTES, sel);
    } else {
        ReadResult result = memory_.read(addr, WORD_BYTES, sel, is_instr_bus_);
        reply.status = result.status;
        reply.data = result.data;
    }

    return reply;
}

void WishboneSlave::on_falling_edge() {
    // A reply lasts for exactly one cycle.
    if (responding_) {
        drive_idle();
        responding_ = false;
    }

    if (delay_left_ > 0) {
        if (--delay_left_ == 0) {
            drive(pending_);
            responding_ = true;
        }
        return;
    }

    if (!(*signals_.cyc && *signals_.stb)) {
        return;
    }

    pending_ = handle_request();

    if (delay_ == 0) {
        drive(pending_);
        responding_ = true;
    } else {
        delay_left_ = delay_;
    }
}

}  // namespace cxxsim
