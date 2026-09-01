#include "memory.h"

#include <pybind11/stl.h>

#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>

namespace cxxsim {

namespace {

uint32_t byte_sel_mask(uint8_t byte_sel, uint8_t byte_count) {
    uint32_t mask = 0;
    for (uint8_t i = 0; i < byte_count; i++) {
        if ((byte_sel >> i) & 1) {
            mask |= UINT32_C(0xff) << (8 * i);
        }
    }
    return mask;
}

[[noreturn]] void fail(const char* what, uint32_t addr) {
    char buffer[128];
    std::snprintf(buffer, sizeof(buffer), "%s: %08x", what, addr);
    throw std::runtime_error(buffer);
}

}  // namespace

RamSegment::RamSegment(uint64_t start, uint64_t end, uint32_t flags, std::vector<uint8_t> data)
    : MemorySegment(start, end, flags), data_(std::move(data)) {
    if (data_.size() != end - start) {
        throw std::runtime_error("RAM segment contents do not match the length of its address range");
    }
}

ReadResult RamSegment::read(uint32_t addr, uint8_t byte_count, uint8_t /*byte_sel*/, bool /*exec*/) {
    uint32_t data = 0;
    std::memcpy(&data, data_.data() + (addr - start()), byte_count);
    return ReadResult{ReplyStatus::Ok, data};
}

ReplyStatus RamSegment::write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) {
    uint8_t* dst = data_.data() + (addr - start());

    uint32_t mask = byte_sel_mask(byte_sel, byte_count);
    uint32_t old = 0;
    std::memcpy(&old, dst, byte_count);

    uint32_t merged = (old & ~mask) | (data & mask);
    std::memcpy(dst, &merged, byte_count);

    return ReplyStatus::Ok;
}

ReadResult CallbackSegment::read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) {
    py::gil_scoped_acquire gil;

    auto reply = on_read_(addr - start(), byte_count, byte_sel, exec).cast<std::pair<ReplyStatus, uint32_t>>();
    return ReadResult{reply.first, reply.second};
}

ReplyStatus CallbackSegment::write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) {
    py::gil_scoped_acquire gil;

    return on_write_(addr - start(), data, byte_count, byte_sel).cast<ReplyStatus>();
}

void MemoryMap::add_segment(std::unique_ptr<MemorySegment> segment) {
    segments_.push_back(std::move(segment));
}

MemorySegment* MemoryMap::find(uint32_t addr) {
    for (auto& segment : segments_) {
        if (segment->contains(addr)) {
            return segment.get();
        }
    }
    return nullptr;
}

ReadResult MemoryMap::read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) {
    MemorySegment* segment = find(addr);
    if (segment == nullptr) {
        // The core may issue undefined reads speculatively.
        if (fail_on_undefined_read_) {
            fail("Undefined read", addr);
        }
        return ReadResult{ReplyStatus::Error, 0};
    }

    if (!segment->has_flag(SEGMENT_READ)) {
        fail("Tried to read from non-read memory", addr);
    }
    if (exec && !segment->has_flag(SEGMENT_EXECUTABLE)) {
        fail("Memory is not executable", addr);
    }
    if (static_cast<uint64_t>(addr) + byte_count > segment->end()) {
        fail("Read crosses a segment boundary", addr);
    }

    return segment->read(addr, byte_count, byte_sel, exec);
}

ReplyStatus MemoryMap::write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) {
    MemorySegment* segment = find(addr);
    if (segment == nullptr) {
        if (fail_on_undefined_write_) {
            fail("Undefined write", addr);
        }
        return ReplyStatus::Error;
    }

    if (!segment->has_flag(SEGMENT_WRITE)) {
        fail("Tried to write to non-writable memory", addr);
    }
    if (static_cast<uint64_t>(addr) + byte_count > segment->end()) {
        fail("Read crosses a segment boundary", addr);
    }

    return segment->write(addr, data, byte_count, byte_sel);
}

}  // namespace cxxsim
