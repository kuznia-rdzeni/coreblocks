from hypothesis import given, strategies as st, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize
from transactron.testing import *
from transactron.lib.storage import ContentAddressableMemory

class TestContentAddressableMemory(TestCaseWithSimulator):
    addr_width = 4
    content_width = 5
    test_number = 50
    addr_layout = data_layout(addr_width)
    content_layout = data_layout(content_width)

    def setUp(self):
        self.entries_count = 8

        self.circ = SimpleTestCircuit(
            ContentAddressableMemory(self.addr_layout, self.content_layout, self.entries_count)
        )

        self.memory = {}

    def generic_process(self, method, input_lst, behaviour_check = None, state_change = None, input_verification = None, settle_count = 0):
        def f():
            while input_lst:
                elem = input_lst.pop()
                if elem == OpNOP():
                    yield
                    continue
                if input_verification is not None and not input_verification(elem):
                    continue
                response = yield from method.call(**elem)
                yield from self.multi_settle(settle_count)
                if behaviour_check is not None:
                    # Here accesses to circuit are allowed
                    yield from behaviour_check(elem, response)
                yield Tick("sync_neg")
                if state_change is not None:
                    # It is standard python function by purpose to don't allow accessing circuit
                    yield from self.multi_settle(settle_count)
                    state_change(elem, response)
        return f

    def push_process(self, in_push):
        def verify_in(elem):
            return not (frozenset(elem["addr"].items()) in self.memory)
        def modify_state(elem, response):
            self.memory[frozenset(elem["addr"].items())] = elem["data"]
        return self.generic_process(self.circ.push, in_push, state_change = modify_state, input_verification = verify_in, settle_count = 1)

    def read_process(self, in_read):
        def check(elem, response):
            addr = elem["addr"]
            frozen_addr = frozenset(addr.items())
            if frozen_addr in self.memory:
                assert response["not_found"]== 0
                assert response["data"]== self.memory[frozen_addr]
            else:
                assert response["not_found"]== 1
        return self.generic_process(self.circ.read, in_read, behaviour_check = check)

    def remove_process(self, in_remove):
        def modify_state(elem, response):
            if frozenset(elem["addr"].items()) in self.memory:
                del self.memory[frozenset(elem["addr"].items())]
        return self.generic_process(self.circ.push, in_remove, state_change = modify_state, settle_count = 2)

    def write_process(self, in_write):
        def verify_in(elem):
            return frozenset(elem["addr"].items()) in self.memory
        def modify_state(elem, response):
            self.memory[frozenset(elem["addr"].items())] = elem["data"]
        return self.generic_process(self.circ.push, in_write, state_change = modify_state, input_verification = verify_in, settle_count = 1)

    @settings(max_examples=10)
    @given(
           generate_process_input(test_number, 3, [("addr", addr_layout), ("data", content_layout)]),
           generate_process_input(test_number, 3, [("addr", addr_layout), ("data", content_layout)]),
           generate_process_input(test_number, 3, [("addr", addr_layout)]),
           generate_process_input(test_number, 3, [("addr", addr_layout)]),
           )
    def test_random(self, in_push, in_write, in_read, in_remove):
        with self.reinitialize_fixtures():
            self.setUp()
            with self.run_simulation(self.circ) as sim:
                sim.add_sync_process(self.push_process(in_push))
                sim.add_sync_process(self.read_process(in_read))
                sim.add_sync_process(self.write_process(in_read))
                sim.add_sync_process(self.remove_process(in_read))
