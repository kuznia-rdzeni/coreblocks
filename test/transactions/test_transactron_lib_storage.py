from hypothesis import given, strategies as st, settings
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize
from transactron.testing import *
from transactron.lib.storage import ContentAddressableMemory

class TestContentAddressableMemory(TestCaseWithSimulator, TransactronHypothesis):
    addr_width = 4
    content_width = 5
    addr_layout = data_layout(addr_width)
    content_layout = data_layout(content_width)

    def setUp(self):
        print("setup")
        self.test_number = 50
        self.entries_count = 8

        self.circ = SimpleTestCircuit(
            ContentAddressableMemory(self.addr_layout, self.content_layout, self.entries_count)
        )

        self.memory = {}

    def input_process(self, hp_data):
        def f():
            yield Settle()
            for _ in self.shrinkable_loop(self.test_number, hp_data):
                addr = hp_data.draw(generate_based_on_layout(self.addr_layout).filter(lambda x: frozenset(x.items()) not in self.memory))
                content = hp_data.draw(generate_based_on_layout(self.content_layout))
                yield from self.circ.push.call(addr=addr, data=content)
                yield Settle()
                self.memory[frozenset(addr.items())] = content
                print(_)
                print("SRODEK")
            print("I_END")
        return f

    def output_process(self, hp_data):
        def f():
            print("OUT_PROC")
            yield Passive()
            while True:
                addr = hp_data.draw(generate_based_on_layout(self.addr_layout))
                res = yield from self.circ.pop.call(addr=addr)
                frozen_addr = frozenset(addr.items())
                if frozen_addr in self.memory:
                    assert res["not_found"]== 0
                    assert res["data"]== self.memory[frozen_addr]
                    self.memory.pop(frozen_addr)
                else:
                    assert res["not_found"]== 1
        return f

#    @rule()
#    def smok(self):
#        pass 
    @given(st.data())
    def test_random(self, hp_data):
        self.manual_setup_method()
        self.setUp()
        print("SMOK",flush=True)
        with DependencyContext(self.dependency_manager):
            with self.run_simulation(self.circ) as sim:
                sim.add_sync_process(self.input_process( hp_data))
                sim.add_sync_process(self.output_process(hp_data))

#    def teardown(self):
#        print("teardownm")
#        TestCaseWithSimulator.dependency_manager=DependencyManager()

#settings.register_profile("ci", max_examples=30, stateful_step_count=1)
#settings.load_profile("ci")
#TestContentAddressableMemory.TestCase.settings=settings(max_examples=10, stateful_step_count=1)
#TestTT = TestContentAddressableMemory.TestCase
class TestClass:
    def test_one(self):
        x = "this"
        assert "h" in x

    def test_two(self):
        x = "hello"
        assert hasattr(x, "check")
