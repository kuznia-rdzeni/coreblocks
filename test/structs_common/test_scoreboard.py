from amaranth import *
from test.common import *
from coreblocks.params import *
from coreblocks.params.configurations import *
from coreblocks.structs_common.scoreboard import *
from parameterized import parameterized


class TestScoreboard(TestCaseWithSimulator):
    def setUp(self):
        random.seed(14)

        self.test_number = 50
        self.entries_count = 9
        self.superscalarity = 4

        self.virtual_scoreboard = defaultdict(int)

    def create_process(self, k, forward):
        def f():
            for _ in range(self.test_number):
                id = random.randrange(self.entries_count)
                dirty = yield from self.circ.get_dirty_list[k].call(id=id)
                if forward:
                    yield Settle()
                self.assertEqual(dirty["dirty"], self.virtual_scoreboard[id])
                new_dirty = random.randrange(2)
                yield from self.circ.set_dirty_list[k].call(id=id, dirty=new_dirty)
                if not forward:
                    yield Settle()
                self.virtual_scoreboard[id] = new_dirty
                yield from self.tick(random.randrange(3))

        return f

    @parameterized.expand([(False,), (True,)])
    def test_random(self, forward):
        self.circ = SimpleTestCircuit(Scoreboard(self.entries_count, self.superscalarity, data_forward=forward))
        with self.run_simulation(self.circ) as sim:
            for k in range(self.superscalarity):
                sim.add_sync_process(self.create_process(k, forward))

    def conflict_process(self):
        yield from self.circ.set_dirty_list[0].call_init(id=0, dirty=0)
        yield from self.circ.set_dirty_list[1].call_init(id=0, dirty=0)
        yield Settle()
        yield
        self.assertEqual((yield from self.circ.set_dirty_list[0].done()), 1)
        self.assertEqual((yield from self.circ.set_dirty_list[1].done()), 0)

    def test_conflict(self):
        self.circ = SimpleTestCircuit(Scoreboard(self.entries_count, self.superscalarity, data_forward=False))
        with self.run_simulation(self.circ) as sim:
            sim.add_sync_process(self.conflict_process)
