from datetime import timedelta
from hypothesis import given, settings, Phase
from transactron.testing import *
from transactron.lib.storage import ContentAddressableMemory


class TestContentAddressableMemory(TestCaseWithSimulator):
    addr_width = 4
    content_width = 5
    test_number = 30
    nop_number = 3
    addr_layout = data_layout(addr_width)
    content_layout = data_layout(content_width)

    def setUp(self):
        self.entries_count = 8

        self.circ = SimpleTestCircuit(
            ContentAddressableMemory(self.addr_layout, self.content_layout, self.entries_count)
        )

        self.memory = {}

    def generic_process(
        self,
        method,
        input_lst,
        behaviour_check=None,
        state_change=None,
        input_verification=None,
        settle_count=0,
        name="",
    ):
        def f():
            while input_lst:
                # wait till all processes will end the previous cycle
                yield from self.multi_settle(4)
                elem = input_lst.pop()
                if isinstance(elem, OpNOP):
                    yield
                    continue
                if input_verification is not None and not input_verification(elem):
                    yield
                    continue
                response = yield from method.call(**elem)
                yield from self.multi_settle(settle_count)
                if behaviour_check is not None:
                    # Here accesses to circuit are allowed
                    ret = behaviour_check(elem, response)
                    if isinstance(ret, Generator):
                        yield from ret
                if state_change is not None:
                    # It is standard python function by purpose to don't allow accessing circuit
                    state_change(elem, response)
                yield

        return f

    def push_process(self, in_push):
        def verify_in(elem):
            return not (frozenset(elem["addr"].items()) in self.memory)

        def modify_state(elem, response):
            self.memory[frozenset(elem["addr"].items())] = elem["data"]

        return self.generic_process(
            self.circ.push,
            in_push,
            state_change=modify_state,
            input_verification=verify_in,
            settle_count=3,
            name="push",
        )

    def read_process(self, in_read):
        def check(elem, response):
            addr = elem["addr"]
            frozen_addr = frozenset(addr.items())
            if frozen_addr in self.memory:
                assert response["not_found"] == 0
                assert response["data"] == self.memory[frozen_addr]
            else:
                assert response["not_found"] == 1

        return self.generic_process(self.circ.read, in_read, behaviour_check=check, settle_count=0, name="read")

    def remove_process(self, in_remove):
        def modify_state(elem, response):
            if frozenset(elem["addr"].items()) in self.memory:
                del self.memory[frozenset(elem["addr"].items())]

        return self.generic_process(self.circ.remove, in_remove, state_change=modify_state, settle_count=2, name="remv")

    def write_process(self, in_write):
        def verify_in(elem):
            ret = frozenset(elem["addr"].items()) in self.memory
            return ret

        def check(elem, response):
            assert response["not_found"] == int(frozenset(elem["addr"].items()) not in self.memory)

        def modify_state(elem, response):
            if frozenset(elem["addr"].items()) in self.memory:
                self.memory[frozenset(elem["addr"].items())] = elem["data"]

        return self.generic_process(
            self.circ.write,
            in_write,
            behaviour_check=check,
            state_change=modify_state,
            input_verification=None,
            settle_count=1,
            name="writ",
        )

    @settings(
        max_examples=10,
        phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink),
        derandomize=True,
        deadline=timedelta(milliseconds=500),
    )
    @given(
        generate_process_input(test_number, nop_number, [("addr", addr_layout), ("data", content_layout)]),
        generate_process_input(test_number, nop_number, [("addr", addr_layout), ("data", content_layout)]),
        generate_process_input(test_number, nop_number, [("addr", addr_layout)]),
        generate_process_input(test_number, nop_number, [("addr", addr_layout)]),
    )
    def test_random(self, in_push, in_write, in_read, in_remove):
        with self.reinitialize_fixtures():
            self.setUp()
            with self.run_simulation(self.circ, max_cycles=500) as sim:
                sim.add_sync_process(self.push_process(in_push))
                sim.add_sync_process(self.read_process(in_read))
                sim.add_sync_process(self.write_process(in_write))
                sim.add_sync_process(self.remove_process(in_remove))
