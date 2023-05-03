from dataclasses import dataclass
import functools
from contextlib import contextmanager, nullcontext
from typing import Callable, Generic, Mapping, Union, Generator, TypeVar, Optional, Any, cast
from enum import Enum, auto
from collections import deque

from amaranth import *
from amaranth.hdl.ast import Statement
from amaranth.sim import *
from amaranth.sim.core import Command

__all__ = ['SimulatorWrapper', 'WaitReadOnly']

T = TypeVar("T")

#TODO: - read-only-phase, początkowy odstęp, muteksy, zmienne warunkowe
# Narzut czasowy: 2%-3%

class CoreblockSimulationError(RuntimeError):
    pass

class CoreblockCommand():
    pass

class CoreblockSimulationEvent():
    pass

class CondVar(CoreblockSimulationEvent):
    def __init__(self):
        self.wait_queue : deque['SyncProcessWrapper'] = deque()

@dataclass
class WaitFor(CoreblockCommand):
    event : CondVar

@dataclass
class Emit(CoreblockCommand):
    event : CondVar

class WaitReadOnly(CoreblockCommand):
    pass

class SyncProcessState(Enum):
    Invalid = auto()
    Running = auto()
    WaitNextCycle = auto()
    WaitReadOnly = auto()
    WaitFor = auto()
    BeginingOfNewCycle = auto()

class SimulationState(Enum):
    Normal = auto()
    ReadOnly = auto()
    NextCycle = auto()

class SyncProcessWrapper():
    def __init__(self, simulator : 'SimulatorWrapper', proc):
        self.org_proc = proc
        self.state = SyncProcessState.Running
        self.simulator = simulator

    def expect_simulation_state(self, sim_state):
        if self.simulator.state != sim_state:
            raise CoreblockSimulationError(f"Wrong simulation state, expected: {sim_state} current: {self.simulator.state}")

    def change_state(self, new_state):
        if new_state == SyncProcessState.BeginingOfNewCycle:
            raise RuntimeError("State BeginingOfNewCycle can be set only by SimulatorWrapper.")
        self.state = new_state
        self.simulator.process_state_changed()

    def wait_next_cycle(self):
        self.change_state(SyncProcessState.WaitNextCycle)
        yield
        self.change_state(SyncProcessState.Running)

    def wait_read_only(self):
        self.change_state(SyncProcessState.WaitReadOnly)
        while self.simulator.state != SimulationState.ReadOnly:
            yield Settle()
        self.change_state(SyncProcessState.Running)

    def handle_statement(self, cmd):
        self.expect_simulation_state(SimulationState.Normal)
        return (yield cmd)
    
    def wait_for(self, cmd : WaitFor):
        self.change_state(SyncProcessState.WaitFor)
        
        cmd.event.wait_queue.append(self)
        while True:
            while self.simulator.state != SimulationState.NextCycle:
                if self.state == SyncProcessState.Running:
                    return
                yield Settle()
            self.change_state(SyncProcessState.WaitNextCycle)
            yield
            self.change_state(SyncProcessState.WaitFor)

    def handle_emit(self, cmd: Emit):
        for p in cmd.event.wait_queue:
            p.change_state(SyncProcessState.Running)

    def _wrapping_function(self):
        response = None
        org_corutine = self.org_proc()
        try:
            while True:
                # call orginal test process and catch data yielded by it in `command` variable
                command = org_corutine.send(response)
                if command is None:
                    yield from self.wait_next_cycle()
                elif type(command) is Statement:
                    response = yield from self.handle_statement(command)
                elif type(command) is WaitReadOnly:
                    yield from self.wait_read_only()
                elif type(command) is Emit:
                    self.handle_emit(command)
                elif type(command) is WaitFor:
                    yield from self.wait_for(command)
                # Pass everything else to amaranth simulator without modifications
                else:
                    response = yield command
        except StopIteration:
            self.change_state(SyncProcessState.WaitNextCycle)

class SimulatorWrapper():
    def __init__(self, module, clk_period, max_cycles):
        self.clk_period = clk_period
        self.module = module
        self.max_cycles = max_cycles

        self.process_list : list[SyncProcessWrapper] = []
        self.state : SimulationState = SimulationState.Normal

        self.sim = Simulator(self.module)
        self.sim.add_clock(self.clk_period)

    def add_sync_process(self, org_proc):
        proc = SyncProcessWrapper(self, org_proc)
        self.process_list.append(proc)
        self.sim.add_sync_process(proc._wrapping_function)

    def _process_state_changed_in_read_only(self):
        all_next_cycle = all(self._transform_proces_list(lambda p: (p.state == SyncProcessState.WaitNextCycle) or (p.state == SyncProcessState.WaitFor)))
        if all_next_cycle:
            if any(self._transform_proces_list(lambda p: (p.state == SyncProcessState.WaitFor))):
                self.state = SimulationState.NextCycle
            else:
                self._start_new_cycle()

    @staticmethod
    def _process_waiting(p : SyncProcessWrapper):
        return (p.state == SyncProcessState.WaitReadOnly) or (p.state == SyncProcessState.WaitNextCycle) or (p.state == SyncProcessState.WaitFor)

    def _transform_proces_list(self, f : Callable[[SyncProcessWrapper], T]) -> list[T]:
        return [f(p) for p in self.process_list]

    def _start_new_cycle(self):
        self.state = SimulationState.Normal
        for p in self.process_list:
            p.state = SyncProcessState.BeginingOfNewCycle

    def _process_state_changed_in_normal(self):
        any_wait_read_only = any([ (p.state == SyncProcessState.WaitReadOnly) for p in self.process_list ])
        any_wait_for = any(self._transform_proces_list(lambda p: (p.state == SyncProcessState.WaitFor)))
        all_wait = all(self._transform_proces_list(self._process_waiting))
        if all_wait:
            if any_wait_read_only:
                self.state = SimulationState.ReadOnly
            elif any_wait_for:
                self.state = SimulationState.NextCycle
            else:
                self._start_new_cycle()

    def _process_state_changed_in_next_state(self):
        all_next_cycle = all(self._transform_proces_list(lambda p: (p.state == SyncProcessState.WaitNextCycle)))
        if all_next_cycle:
            self._start_new_cycle()

    def process_state_changed(self):
        if self.state == SimulationState.Normal:
            self._process_state_changed_in_normal()
        elif self.state == SimulationState.ReadOnly:
            self._process_state_changed_in_read_only()
        elif self.state == SimulationState.NextCycle:
            self._process_state_changed_in_next_state()

    def run_until(self, ctx):
        with ctx:
            self.sim.run_until(self.clk_period * self.max_cycles)
            assert self.sim.advance() == False, "Simulation time limit exceeded"
