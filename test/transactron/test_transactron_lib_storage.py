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

    def input_process(self, in_push):
        def f():
            yield Settle()
            for addr, content in in_push:
                if frozenset(addr.items()) in self.memory:
                    continue
                yield from self.circ.push.call(addr=addr, data=content)
                yield Settle()
                self.memory[frozenset(addr.items())] = content
        return f

    def output_process(self, in_pop):
        def f():
            yield Passive()
            while in_pop:
                addr = in_pop.pop()
                res = yield from self.circ.pop.call(addr=addr)
                frozen_addr = frozenset(addr.items())
                if frozen_addr in self.memory:
                    assert res["not_found"]== 0
                    assert res["data"]== self.memory[frozen_addr]
                    self.memory.pop(frozen_addr)
                else:
                    assert res["not_found"]== 1
        return f

    @settings(max_examples=10)
    @given(generate_shrinkable_list(test_number, st.tuples(generate_based_on_layout(addr_layout), generate_based_on_layout(content_layout))),
           generate_shrinkable_list(test_number, generate_based_on_layout(addr_layout)))
    def test_random(self, in_push, in_pop):
        with self.reinitialize_fixtures():
            self.setUp()
            with self.run_simulation(self.circ) as sim:
                sim.add_sync_process(self.input_process(in_push))
                sim.add_sync_process(self.output_process(in_pop))
