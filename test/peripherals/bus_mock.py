from amaranth import *
from dataclasses import dataclass
from transactron import TModule
from transactron.testing import TestbenchIO
from transactron.lib.adapters import Adapter
from coreblocks.peripherals.bus_adapter import BusParametersInterface, BusMasterInterface, CommonBusMasterMethodLayout


__all__ = ["BusMockParameters", "MockMasterAdapter"]


@dataclass
class BusMockParameters(BusParametersInterface):
    data_width: int
    addr_width: int
    granularity: int = 8


class MockMasterAdapter(Elaboratable, BusMasterInterface):
    def __init__(self, params: BusMockParameters):
        self.params = params
        self.method_layouts = CommonBusMasterMethodLayout(params)

        self.request_read_mock = TestbenchIO(Adapter.create(i=self.method_layouts.request_read_layout))
        self.request_write_mock = TestbenchIO(Adapter.create(i=self.method_layouts.request_write_layout))
        self.get_read_response_mock = TestbenchIO(Adapter.create(o=self.method_layouts.read_response_layout))
        self.get_write_response_mock = TestbenchIO(Adapter.create(o=self.method_layouts.write_response_layout))
        self.request_read = self.request_read_mock.adapter.iface
        self.request_write = self.request_write_mock.adapter.iface
        self.get_read_response = self.get_read_response_mock.adapter.iface
        self.get_write_response = self.get_write_response_mock.adapter.iface

    def elaborate(self, platform):
        m = TModule()

        m.submodules.request_read_mock = self.request_read_mock
        m.submodules.request_write_mock = self.request_write_mock
        m.submodules.get_read_response = self.get_read_response_mock
        m.submodules.get_write_response = self.get_write_response_mock

        return m
