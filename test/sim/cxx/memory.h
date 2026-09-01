#pragma once

#include <pybind11/pybind11.h>

#include <cstdint>
#include <memory>
#include <vector>

namespace cxxsim {

namespace py = pybind11;

// Mirrors SegmentFlags in memory.py.
enum SegmentFlags : uint32_t {
    SEGMENT_READ = 1,
    SEGMENT_WRITE = 2,
    SEGMENT_EXECUTABLE = 4,
};

// Mirrors ReplyStatus in memory.py.
enum class ReplyStatus : uint8_t {
    Ok = 0,
    Error = 1,
    Retry = 2,
};

struct ReadResult {
    ReplyStatus status = ReplyStatus::Ok;
    uint32_t data = 0;
};

class MemorySegment {
  public:
    MemorySegment(uint64_t start, uint64_t end, uint32_t flags) : start_(start), end_(end), flags_(flags) {}
    virtual ~MemorySegment() = default;

    bool contains(uint64_t addr) const { return addr >= start_ && addr < end_; }

    uint64_t start() const { return start_; }
    uint64_t end() const { return end_; }
    uint32_t flags() const { return flags_; }
    bool has_flag(SegmentFlags flag) const { return (flags_ & flag) != 0; }

    virtual ReadResult read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) = 0;
    virtual ReplyStatus write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) = 0;

  private:
    uint64_t start_;
    uint64_t end_;
    uint32_t flags_;
};

class RamSegment : public MemorySegment {
  public:
    RamSegment(uint64_t start, uint64_t end, uint32_t flags, std::vector<uint8_t> data);

    ReadResult read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) override;
    ReplyStatus write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) override;

  private:
    std::vector<uint8_t> data_;
};

// A segment whose accesses are handled by Python callables.
class CallbackSegment : public MemorySegment {
  public:
    CallbackSegment(uint64_t start, uint64_t end, uint32_t flags, py::object on_read, py::object on_write)
        : MemorySegment(start, end, flags), on_read_(std::move(on_read)), on_write_(std::move(on_write)) {}

    ReadResult read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) override;
    ReplyStatus write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) override;

  private:
    py::object on_read_;
    py::object on_write_;
};

class MemoryMap {
  public:
    MemoryMap(bool fail_on_undefined_read, bool fail_on_undefined_write)
        : fail_on_undefined_read_(fail_on_undefined_read), fail_on_undefined_write_(fail_on_undefined_write) {}

    void add_segment(std::unique_ptr<MemorySegment> segment);

    ReadResult read(uint32_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec);
    ReplyStatus write(uint32_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel);

  private:
    MemorySegment* find(uint32_t addr);

    std::vector<std::unique_ptr<MemorySegment>> segments_;
    bool fail_on_undefined_read_;
    bool fail_on_undefined_write_;
};

}  // namespace cxxsim
