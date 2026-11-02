from collections.abc import Callable, Sequence
from dataclasses import dataclass
from collections import defaultdict, deque
import random
from typing import Any
import pytest
import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings
from transactron.lib.adapters import Adapter
from transactron.testing.functions import data_const_to_dict
from transactron.testing.method_mock import MethodMock, def_method_mocks
from transactron.utils import DependencyContext, ModuleConnector
from transactron.testing.input_generation import amaranth_consts, amaranth_structs, draw_wait_geom, shrinkable_lists
from coreblocks.interface.keys import CoreStateKey
from coreblocks.interface.layouts import (
    CommonLayoutFields,
    RATLayouts,
    RetirementLayouts,
    RFLayouts,
    SchedulerLayouts,
)
from coreblocks.params import GenParams, configurations
from coreblocks.arch import OpType
from coreblocks.arch.optypes import impure_optypes
from coreblocks.scheduler.scheduler import Scheduler
from transactron.testing import (
    SimpleTestCircuit,
    TestCaseWithSimulator,
    TestbenchContext,
    TestbenchIO,
    def_method_mock,
)
from .test_scheduler import MockedBlockComponent


@st.composite
def sample_optype_sets(draw: st.DrawFn):
    optype_pool = draw(st.lists(st.sampled_from(OpType), min_size=1, max_size=4, unique=True))
    return draw(st.lists(st.sets(st.sampled_from(optype_pool), min_size=1), min_size=1, max_size=4))


def rand_enable(data: st.DataObject) -> Callable[[], bool]:
    rnd = random.Random(data.draw(st.integers(0, 2**32-1), label="rng_seed"))
    p = data.draw(st.sampled_from([1.0, 0.9, 0.7, 0.5]), label="enable_prob")
    return lambda: rnd.random() < p


def rand_enables(data: st.DataObject, count: int) -> Callable[[int], bool]:
    enables = [rand_enable(data) for _ in range(count)]
    return lambda i: enables[i]()


@dataclass
class Group:
    count: int
    insns: list[dict[str, Any]]
    rp_dsts: list[int]
    rename_resps: list[dict[str, Any]]
    rf_s1s: list[dict[str, Any]]
    rf_s2s: list[dict[str, Any]]
    tag_resp: dict[str, Any]


@dataclass
class Instr:
    insn: dict[str, Any]
    tag: int
    way: int
    rp_dst: int
    rp_s1: int
    rp_s2: int
    rf_s1: dict[str, Any]
    rf_s2: dict[str, Any]


class TestScheduler2(TestCaseWithSimulator):  # TODO: rename
    @pytest.mark.parametrize("ways", [1, 2, 4])
    @given(rs_entries=st.integers(3, 8), optype_sets=sample_optype_sets(), data=st.data())
    @settings(deadline=None, max_examples=2, suppress_health_check=[HealthCheck.large_base_example])
    def test_scheduler(self, rs_entries: int, ways: int, optype_sets: Sequence[set[OpType]], data: st.DataObject):
        gen_params = GenParams(
            configurations.test.replace(
                allow_partial_extensions=True,
                frontend_superscalarity=ways,
                func_units_config=tuple(
                    MockedBlockComponent(optypes, rs_entries=rs_entries)
                    for optypes in optype_sets
                ),
            )
        )

        # Generate inputs together with responses of the mocked components
        layouts = gen_params.get(SchedulerLayouts)
        fields = gen_params.get(CommonLayoutFields)
        rat_layouts = gen_params.get(RATLayouts)
        rf_layouts = gen_params.get(RFLayouts)
        optype_set: list[OpType] = list(set.union(*optype_sets))

        @st.composite
        def instr_groups(draw: st.DrawFn) -> Group:
            count = draw(st.integers(1, ways))
            # instructions past `count` are garbage which should be ignored
            insns = [
                draw(
                    amaranth_structs(
                        layouts.reg_alloc_in_data,
                        exec_fn=amaranth_structs(fields.exec_fn_layout, op_type=st.sampled_from(optype_set)),
                    )
                )
                for _ in range(ways)
            ]
            rp_dsts = [draw(amaranth_consts(gen_params.phys_regs_bits)) for _ in range(count)]
            rename_resps = [
                draw(amaranth_structs(rat_layouts.crat_rename_out))
                for _ in range(count)
            ]
            rf_s1s = [draw(amaranth_structs(rf_layouts.rf_read_out)) for _ in range(count)]
            rf_s2s = [draw(amaranth_structs(rf_layouts.rf_read_out)) for _ in range(count)]
            tag_resp = draw(amaranth_structs(rat_layouts.crat_tag_out))
            return Group(
                count=count,
                insns=insns,
                rp_dsts=rp_dsts,
                rename_resps=rename_resps,
                rf_s1s=rf_s1s,
                rf_s2s=rf_s2s,
                tag_resp=tag_resp,
            )

        groups: list[Group] = data.draw(shrinkable_lists(25, instr_groups()))
        group_first: list[int] = []
        instrs: list[Instr] = []
        for group in groups:
            group_first.append(len(instrs))
            for i, (insn, rp_dst, rename_resp, rf_s1, rf_s2) in enumerate(
                zip(group.insns, group.rp_dsts, group.rename_resps, group.rf_s1s, group.rf_s2s)
            ):
                instrs.append(
                    Instr(
                        insn=insn,
                        tag=group.tag_resp["tag"],
                        way=i,
                        rp_dst=rp_dst if insn["regs_l"]["rl_dst"] != 0 else 0,
                        rp_s1=rename_resp["rp_s1"],
                        rp_s2=rename_resp["rp_s2"],
                        rf_s1=rf_s1,
                        rf_s2=rf_s2,
                    )
                )

        def rob_id(n: int) -> int:
            return n % 2**gen_params.rob_entries_bits

        # Create DUT
        sched = SimpleTestCircuit(Scheduler(gen_params=gen_params))

        core_state = TestbenchIO(Adapter(o=gen_params.get(RetirementLayouts).core_state, nonexclusive=True))
        dm = DependencyContext.get()
        dm.add_dependency(CoreStateKey(), core_state.adapter.iface)

        m = ModuleConnector(sched=sched, core_state=core_state)

        # Expectation queues: which group/instruction each mock serves next
        tag_q = deque(range(len(groups)))
        commit_q = deque(range(len(groups)))
        rob_q = deque(range(len(groups)))
        rename_q: list[deque[int]] = [deque() for _ in range(ways)]
        free_reg_q: list[deque[int]] = [deque() for _ in range(ways)]
        rf_req_q = deque(range(len(instrs)))
        rob_to_instr: dict[int, deque[int]] = defaultdict(deque)
        for n, instr in enumerate(instrs):
            rename_q[instr.way].append(n)
            if instr.insn["regs_l"]["rl_dst"] != 0:
                free_reg_q[instr.way].append(n)
            rob_to_instr[rob_id(n)].append(n)

        # Run-time state of the mocks
        rf_pending: list[deque[int]] = [deque() for _ in sched.rf_read_req]
        selected: list[deque[int]] = [deque() for _ in optype_sets]
        last_inserted = [-1 for _ in optype_sets]
        inserted = [False for _ in instrs]

        rs_rnd = random.Random(data.draw(st.integers(0, 2**32)))
        next_entry = [rs_rnd.randrange(rs_entries) for _ in optype_sets]

        async def get_instr(ctx: TestbenchContext):
            for group in groups:
                await sched.get_instr.call(ctx, count=group.count, data=group.insns)
                await draw_wait_geom(ctx, data, 0.1)

        @def_method_mocks(sched.get_free_reg, enable=rand_enables(data, ways))
        def get_free_reg(i):
            n = free_reg_q[i][0] if free_reg_q[i] else None

            @MethodMock.effect
            def _():
                assert n is not None, f"unexpected get_free_reg[{i}] call"
                free_reg_q[i].popleft()

            return {"ident": instrs[n].rp_dst if n is not None else 0}

        @def_method_mock(sched.crat_tag, enable=rand_enable(data))
        def crat_tag(rollback_tag, rollback_tag_v, commit_checkpoint):
            g = tag_q[0] if tag_q else None

            @MethodMock.effect
            def _():
                assert g is not None, "unexpected crat_tag call"
                group = groups[g]
                last = group.insns[group.count - 1]
                assert rollback_tag == last["rollback_tag"]
                assert rollback_tag_v == last["rollback_tag_v"]
                assert commit_checkpoint == last["commit_checkpoint"]
                tag_q.popleft()

            return groups[g].tag_resp if g is not None else None

        @def_method_mock(sched.crat_commit_checkpoint, enable=rand_enable(data))
        def crat_commit_checkpoint(tag, commit_checkpoint):
            @MethodMock.effect
            def _():
                assert commit_q, "unexpected crat_commit_checkpoint call"
                tag_resp = groups[commit_q.popleft()].tag_resp
                assert tag == tag_resp["tag"]
                assert commit_checkpoint == tag_resp["commit_checkpoint"]

        @def_method_mocks(sched.crat_rename, enable=rand_enables(data, ways))
        def crat_rename(i, rl_s1, rl_s2, rl_dst, rp_dst):
            n = rename_q[i][0] if rename_q[i] else None

            @MethodMock.effect
            def _():
                assert n is not None, f"unexpected crat_rename[{i}] call"
                instr = instrs[n]
                regs_l = instr.insn["regs_l"]
                assert rl_s1 == regs_l["rl_s1"]
                assert rl_s2 == regs_l["rl_s2"]
                assert rl_dst == regs_l["rl_dst"]
                assert rp_dst == instr.rp_dst
                rename_q[i].popleft()

            if n is not None:
                return {"rp_s1": instrs[n].rp_s1, "rp_s2": instrs[n].rp_s2}

        @def_method_mock(sched.crat_active_tags)
        def crat_active_tags() -> dict[str, Any]:
            # TODO: flushing test
            return {"active_tags": [1] * 2**gen_params.tag_bits}

        @def_method_mock(sched.rob_put, enable=rand_enable(data))
        def rob_put(count, entries) -> dict[str, Any]:
            g = rob_q[0] if rob_q else None

            @MethodMock.effect
            def _():
                assert g is not None, "unexpected rob_put call"
                group = groups[g]
                assert count == group.count
                for i in range(count):
                    instr = instrs[group_first[g] + i]
                    insn = instr.insn
                    rob_data = entries[i].rob_data
                    assert rob_data.rl_dst == insn["regs_l"]["rl_dst"]
                    assert rob_data.rp_dst == instr.rp_dst
                    assert rob_data.tag_increment == (group.tag_resp["tag_increment"] if i == 0 else 0)
                    assert data_const_to_dict(rob_data.ftq_ptr) == insn["ftq_ptr"]
                    assert entries[i].pure == (insn["exec_fn"]["op_type"] not in impure_optypes)
                rob_q.popleft()

            first = group_first[g] if g is not None else 0
            return {"entries": [{"rob_id": rob_id(first + i)} for i in range(ways)]}

        def rf_source(n: int, k: int) -> tuple[int, dict[str, Any]]:
            instr = instrs[n]
            return (instr.rp_s1, instr.rf_s1) if k % 2 == 0 else (instr.rp_s2, instr.rf_s2)

        @def_method_mocks(sched.rf_read_req)
        def rf_read_req(k, reg_id):
            n = rf_req_q[k // 2] if len(rf_req_q) > k // 2 else None

            @MethodMock.effect
            def _():
                assert n is not None, f"unexpected rf_read_req[{k}] call"
                assert reg_id == rf_source(n, k)[0]
                rf_pending[k].append(n)
                if k % 2 == 0:
                    rf_req_q.popleft()

        # RS insertion requires the response to be available, so no random enable here
        @def_method_mocks(sched.rf_read_resp, enable=lambda k: bool(rf_pending[k]))
        def rf_read_resp(k, reg_id):
            n = rf_pending[k][0] if rf_pending[k] else None

            @MethodMock.effect
            def _():
                assert n is not None, f"unexpected rf_read_resp[{k}] call"
                assert reg_id == rf_source(n, k)[0]
                rf_pending[k].popleft()

            return rf_source(n, k)[1] if n is not None else None

        @def_method_mocks(sched.rs_select, enable=rand_enables(data, len(optype_sets)))
        def rs_select(j):
            entry = next_entry[j]

            @MethodMock.effect
            def _():
                selected[j].append(entry)
                next_entry[j] = rs_rnd.randrange(rs_entries)

            return {"rs_entry_id": entry}

        @def_method_mocks(sched.rs_insert, enable=rand_enables(data, len(optype_sets)))
        def rs_insert(j, rs_data, rs_entry_id):
            @MethodMock.effect
            def _():
                assert rob_to_instr.get(rs_data.rob_id), f"rs_insert[{j}] with unknown rob_id {rs_data.rob_id}"
                n = rob_to_instr[rs_data.rob_id].popleft()
                instr = instrs[n]
                insn = instr.insn
                assert insn["exec_fn"]["op_type"] in optype_sets[j]
                assert selected[j], f"rs_insert[{j}] without rs_select"
                assert rs_entry_id == selected[j].popleft()
                assert n > last_inserted[j]
                last_inserted[j] = n

                s1 = instr.rf_s1
                s2 = instr.rf_s2
                expected = {
                    "rp_s1": 0 if s1["valid"] else instr.rp_s1,
                    "rp_s2": 0 if s2["valid"] else instr.rp_s2,
                    "rp_s1_reg": instr.rp_s1,
                    "rp_s2_reg": instr.rp_s2,
                    "rp_dst": instr.rp_dst,
                    "rob_id": rob_id(n),
                    "exec_fn": insn["exec_fn"],
                    "s1_val": s1["reg_val"] if s1["valid"] else 0,
                    "s2_val": s2["reg_val"] if s2["valid"] else 0,
                    "imm": insn["imm"],
                    "csr": insn["csr"],
                    "pc": insn["pc"],
                    "tag": instr.tag,
                    "ftq_ptr": insn["ftq_ptr"],
                }
                got = data_const_to_dict(rs_data)
                for key, val in got.items():
                    assert val == expected[key], f"instr {n} field {key}: got {val}, expected {expected[key]}"

                inserted[n] = True

        @def_method_mock(core_state)
        def core_state_mock() -> dict[str, int]:
            # TODO: flushing test
            return {"flushing": 0}

        async def wait_for_completion(ctx: TestbenchContext):
            while not all(inserted):
                await ctx.tick()
            await ctx.tick()

        with self.run_simulation(m, max_cycles=3000) as sim:
            sim.add_testbench(get_instr)
            sim.add_testbench(wait_for_completion)

        assert all(inserted)
        assert not tag_q and not commit_q and not rob_q
        assert not any(rename_q) and not any(free_reg_q)
        assert not rf_req_q and not any(rf_pending)
        assert not any(selected)
