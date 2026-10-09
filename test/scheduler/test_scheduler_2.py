from collections.abc import Sequence
from collections import deque
import pytest
import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings
from transactron.lib.adapters import Adapter
from transactron.testing.method_mock import MethodMock, def_method_mocks
from transactron.utils import DependencyContext, ModuleConnector
from transactron.testing.input_generation import amaranth_structs, draw_wait_geom, shrinkable_lists
from coreblocks.interface.keys import CoreStateKey
from coreblocks.interface.layouts import CommonLayoutFields, RetirementLayouts, SchedulerLayouts
from coreblocks.params import GenParams, configurations
from coreblocks.arch import OpType
from coreblocks.scheduler.scheduler import Scheduler
from transactron.testing import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    TestbenchContext,
    TestbenchIO,
    def_method_mock,
)
from .test_scheduler import MockedBlockComponent


@pytest.mark.parametrize(
    "ways, optype_sets",
    [
        (1, [set(OpType)]),
        (1, [{OpType.ARITHMETIC, OpType.COMPARE}, {OpType.MUL, OpType.COMPARE}, {OpType.DIV_REM, OpType.COMPARE}]),
        (2, [{OpType.ARITHMETIC}, {OpType.ARITHMETIC, OpType.COMPARE}, {OpType.MUL, OpType.DIV_REM}]),
    ],
)
class TestScheduler2(TestCaseWithSimulator):  # TODO: rename
    @given(data=st.data())
    @settings(deadline=None, max_examples=3, suppress_health_check=[HealthCheck.large_base_example])
    def test_scheduler(self, ways: int, optype_sets: Sequence[set[OpType]], data: st.DataObject):
        # Setup DUT
        gen_params = GenParams(
            configurations.test.replace(
                allow_partial_extensions=True,
                frontend_superscalarity=ways,
                func_units_config=tuple(MockedBlockComponent(optypes, rs_entries=4) for optypes in optype_sets),
            )
        )

        sched = SimpleTestCircuit(Scheduler(gen_params=gen_params))

        core_state = TestbenchIO(Adapter(o=gen_params.get(RetirementLayouts).core_state, nonexclusive=True))
        dm = DependencyContext.get()
        dm.add_dependency(CoreStateKey(), core_state.adapter.iface)

        m = ModuleConnector(sched=sched, core_state=core_state)

        # Generate inputs
        layouts = gen_params.get(SchedulerLayouts)
        fields = gen_params.get(CommonLayoutFields)
        optype_set: list[OpType] = list(set.union(*optype_sets))

        @st.composite
        def instructions(draw: st.DrawFn):
            count = draw(st.integers(1, ways))
            insns = []
            for _ in range(count):
                insns.append(
                    draw(
                        amaranth_structs(
                            layouts.reg_alloc_in_data,
                            exec_fn=amaranth_structs(fields.exec_fn_layout, op_type=st.sampled_from(optype_set)),
                        )
                    )
                )
            return {"count": count, "data": insns}

        inputs = deque(data.draw(shrinkable_lists(50, instructions())))

        rf_pending: list[deque[int]] = [deque() for _ in sched.rf_read_req]

        async def get_instr(ctx: TestbenchContext):
            while inputs:
                instrs = inputs.popleft()
                print(instrs)
                await sched.get_instr.call(ctx, instrs)
                await draw_wait_geom(ctx, data, 0.1)

        @def_method_mocks(sched.get_free_reg)
        def get_free_reg(i):
            pass

        @def_method_mocks(sched.crat_rename)
        def crat_rename(i, rl_s1, rl_s2, rl_dst, rp_dst):
            pass

        @def_method_mock(sched.crat_tag)
        def crat_tag(rollback_tag, rollback_tag_v, commit_checkpoint):
            pass

        @def_method_mock(sched.crat_commit_checkpoint)
        def crat_commit_checkpoint(tag, commit_checkpoint):
            pass

        @def_method_mock(sched.crat_active_tags)
        def crat_active_tags():
            pass

        @def_method_mock(sched.rob_put)
        def rob_put(count, entries):
            pass

        @def_method_mocks(sched.rf_read_req)
        def rf_read_req(i, reg_id):
            @MethodMock.effect
            def _():
                rf_pending[i].append(reg_id)

        @def_method_mocks(sched.rf_read_resp, enable=lambda i: bool(rf_pending[i]))
        def rf_read_resp(i, reg_id):
            assert reg_id == rf_pending[i][0]

            @MethodMock.effect
            def _():
                rf_pending[i].popleft()

            return {"reg_val": 0, "valid": 1}

        @def_method_mocks(sched.rs_select)
        def rs_select(k):
            pass

        @def_method_mocks(sched.rs_insert)
        def rs_insert(k, arg):
            pass

        @def_method_mock(core_state)
        def core_state_mock() -> dict[str, int]:
            # TODO: flushing test
            return {"flushing": 0}

        async def keep_alive(ctx: TestbenchContext):
            pass

        with self.run_simulation(m, max_cycles=200) as sim:
            sim.add_testbench(get_instr)
            sim.add_testbench(keep_alive)
