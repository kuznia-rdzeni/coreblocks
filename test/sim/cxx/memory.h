#pragma once

#include <cstdint>
#include <functional>
#include <memory>
#include <utility>
#include <vector>

namespace cxxsim {

using address_t = uint32_t;

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

using ReadResult = std::pair<ReplyStatus, uint32_t>;

using read_callback_t = std::function<ReadResult(address_t, uint8_t, uint8_t, bool)>;
using write_callback_t = std::function<ReplyStatus(address_t, uint32_t, uint8_t, uint8_t)>;

class MemorySegment {
  public:
    MemorySegment(address_t start, address_t end, uint32_t flags) : start_(start), end_(end), flags_(flags) {}
    virtual ~MemorySegment() = default;

    bool contains(address_t addr) const { return addr >= start_ && addr < end_; }

    address_t start() const { return start_; }
    address_t end() const { return end_; }
    uint32_t flags() const { return flags_; }
    bool has_flag(SegmentFlags flag) const { return (flags_ & flag) != 0; }

    virtual ReadResult read(address_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) = 0;
    virtual ReplyStatus write(address_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) = 0;

  private:
    address_t start_;
    address_t end_;
    uint32_t flags_;
};

class RamSegment : public MemorySegment {
  public:
    RamSegment(address_t start, address_t end, uint32_t flags, std::vector<uint8_t> data);

    ReadResult read(address_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) override;
    ReplyStatus write(address_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) override;

  private:
    std::vector<uint8_t> data_;
};

// A segment whose accesses are handled by Python callables.
class CallbackSegment : public MemorySegment {
  public:
    CallbackSegment(address_t start, address_t end, uint32_t flags, read_callback_t on_read,
                    write_callback_t on_write)
        : MemorySegment(start, end, flags), on_read_(std::move(on_read)), on_write_(std::move(on_write)) {}

    ReadResult read(address_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec) override;
    ReplyStatus write(address_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel) override;

  private:
    read_callback_t on_read_;
    write_callback_t on_write_;
};

class MemoryMap {
  public:
    MemoryMap(bool fail_on_undefined_read, bool fail_on_undefined_write)
        : fail_on_undefined_read_(fail_on_undefined_read), fail_on_undefined_write_(fail_on_undefined_write) {}

    void add_segment(std::unique_ptr<MemorySegment> segment);

    ReadResult read(address_t addr, uint8_t byte_count, uint8_t byte_sel, bool exec);
    ReplyStatus write(address_t addr, uint32_t data, uint8_t byte_count, uint8_t byte_sel);

  private:
    MemorySegment* find(address_t addr);

    std::vector<std::unique_ptr<MemorySegment>> segments_;
    bool fail_on_undefined_read_;
    bool fail_on_undefined_write_;
};

}  // namespace cxxsim
