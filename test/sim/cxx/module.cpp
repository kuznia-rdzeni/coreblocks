#include <pybind11/pybind11.h>

#include "memory.h"
#include "simulation.h"

namespace py = pybind11;

PYBIND11_MODULE(coreblocks_cxxsim, m) {
    using namespace cxxsim;

    py::enum_<SegmentFlags>(m, "SegmentFlags", py::arithmetic())
        .value("READ", SEGMENT_READ)
        .value("WRITE", SEGMENT_WRITE)
        .value("EXECUTABLE", SEGMENT_EXECUTABLE);

    py::enum_<ReplyStatus>(m, "ReplyStatus")
        .value("OK", ReplyStatus::Ok)
        .value("ERROR", ReplyStatus::Error)
        .value("RETRY", ReplyStatus::Retry);

    py::enum_<FinishReason>(m, "FinishReason")
        .value("STOPPED", FinishReason::Stopped)
        .value("TIMEOUT", FinishReason::Timeout);

    py::class_<RunResult>(m, "RunResult")
        .def_readonly("reason", &RunResult::reason)
        .def_readonly("cycles", &RunResult::cycles);

    py::class_<Simulation>(m, "Simulation")
        .def(py::init<uint64_t, bool, bool>(), py::arg("timeout_cycles"), py::arg("fail_on_undefined_read"),
             py::arg("fail_on_undefined_write"))
        .def("add_ram", &Simulation::add_ram, py::arg("start"), py::arg("end"), py::arg("flags"), py::arg("data"))
        .def("add_mmio", &Simulation::add_mmio, py::arg("start"), py::arg("end"), py::arg("flags"),
             py::arg("on_read"), py::arg("on_write"))
        .def("request_stop", &Simulation::request_stop)
        .def("set_interrupts", &Simulation::set_interrupts, py::arg("interrupts"))
        .def("run", &Simulation::run);
}
