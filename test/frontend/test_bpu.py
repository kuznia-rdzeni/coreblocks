from collections import deque
from contextlib import ExitStack
from unittest.mock import patch
from dataclasses import dataclass

import pytest
from amaranth import C, Mux, Signal
from transactron import Method, Provided, TModule, def_method
from transactron.lib import Pipe
from transactron.lib.metrics import HwMetricsEnabledKey
from transactron.testing import (
    CallTrigger,
    SimpleTestCircuit,
    TestbenchContext,
    TestCaseWithSimulator,
    def_method_mock,
)
from transactron.testing.method_mock import MethodMock
from transactron.utils import make_layout
from transactron.utils.dependencies import DependencyContext

from coreblocks.arch import CfiType
from coreblocks.frontend.bpu.bpu import BranchPredictionUnit
from coreblocks.frontend.bpu.component import (
    CfiPredictor,
    DirectionPredictor,
    FastPredictor,
)
from coreblocks.params import (
    BranchPredictionConfig,
    CfiPredictorConfig,
    DirectionPredictorConfig,
    FastPredictorConfig,
    GenParams,
    configurations,
)


FAST_META_WIDTH = 4
CFI_META_WIDTH = 8
DIRECTION_META_WIDTH = 8
CANDIDATE_COUNT = 4


@dataclass(frozen=True)
class FastCase:
    pc: int
    valid: int = 0
    cfi_idx: int = 0
    cfi_type: CfiType = CfiType.INVALID
    target_valid: int = 0
    target: int = 0
    meta: int = 0


@dataclass(frozen=True)
class Candidate:
    valid: int = 0
    cfi_idx: int = 0
    cfi_type: CfiType = CfiType.INVALID
    target_valid: int = 0
    target: int = 0


@dataclass(frozen=True)
class CfiCase:
    pc: int
    candidates: tuple[Candidate, ...] = ()
    meta: int = 0


@dataclass(frozen=True)
class DirectionCase:
    pc: int
    taken: int = 0
    meta: int = 0


def as_int(value) -> int:
    return value.value if isinstance(value, CfiType) else value


def lookup(cases, pc, field: str, width: int):
    value = C(0, width)
    for case in cases:
        value = Mux(pc == case.pc, C(as_int(getattr(case, field)), width), value)
    return value


def lookup_cfi_type(m: TModule, cases, pc):
    value = C(CfiType.INVALID.value, CfiType.as_shape().width)
    for case in cases:
        value = Mux(
            pc == case.pc,
            C(getattr(case, "cfi_type").value, CfiType.as_shape().width),
            value,
        )
    result = Signal(CfiType)
    m.d.av_comb += result.eq(value)
    return result


class MockUpdateRecorder:
    update: Provided[Method]

    def record_updates(self, m):
        self.last_update = Signal.like(self.update.data_in)
        self.update_count = Signal(8)

        @def_method(m, self.update)
        def _(arg):
            m.d.sync += [self.last_update.eq(arg), self.update_count.eq(self.update_count + 1)]


class MockFastPredictor(MockUpdateRecorder, FastPredictor):
    def __init__(self, gen_params: GenParams, cases: tuple[FastCase, ...]):
        super().__init__(gen_params, FAST_META_WIDTH)
        self.cases = cases

    def elaborate(self, platform):
        m = TModule()
        request_pc = Signal(self.gen_params.isa.xlen)
        request_valid = Signal()
        m.d.sync += request_valid.eq(self.request_s0.run)

        @def_method(m, self.request_s0)
        def _(pc):
            m.d.sync += request_pc.eq(pc)

        @def_method(m, self.response_s1, ready=request_valid)
        def _():
            return {
                "valid": lookup(self.cases, request_pc, "valid", 1),
                "cfi_idx": lookup(self.cases, request_pc, "cfi_idx", self.gen_params.fetch_width_log),
                "cfi_type": lookup_cfi_type(m, self.cases, request_pc),
                "target_valid": lookup(self.cases, request_pc, "target_valid", 1),
                "target": lookup(self.cases, request_pc, "target", self.gen_params.isa.xlen),
                "meta": lookup(self.cases, request_pc, "meta", self.meta_width),
            }

        self.record_updates(m)

        return m


class MockCfiPredictor(MockUpdateRecorder, CfiPredictor):
    def __init__(self, gen_params: GenParams, cases: tuple[CfiCase, ...]):
        super().__init__(gen_params, CFI_META_WIDTH, CANDIDATE_COUNT)
        self.cases = cases

    def candidate_field(self, pc, way: int, field: str, width: int):
        value = C(0, width)
        for case in self.cases:
            candidate = case.candidates[way] if way < len(case.candidates) else Candidate()
            value = Mux(pc == case.pc, C(as_int(getattr(candidate, field)), width), value)
        return value

    def candidate_cfi_type(self, m: TModule, pc, way: int):
        value = C(CfiType.INVALID.value, CfiType.as_shape().width)
        for case in self.cases:
            candidate = case.candidates[way] if way < len(case.candidates) else Candidate()
            value = Mux(
                pc == case.pc,
                C(candidate.cfi_type.value, CfiType.as_shape().width),
                value,
            )
        result = Signal(CfiType)
        m.d.av_comb += result.eq(value)
        return result

    def elaborate(self, platform):
        m = TModule()
        pc_layout = make_layout(("pc", self.gen_params.isa.xlen))
        m.submodules.s1_pipe = s1_pipe = Pipe(pc_layout)
        m.submodules.s2_pipe = s2_pipe = Pipe(pc_layout)

        @def_method(m, self.request_s0)
        def _(pc):
            s1_pipe.write(m, pc=pc)

        @def_method(m, self.response_s1)
        def _():
            pc = s1_pipe.read(m).pc
            s2_pipe.write(m, pc=pc)
            return {
                "candidates": [
                    {
                        "valid": self.candidate_field(pc, way, "valid", 1),
                        "cfi_idx": self.candidate_field(pc, way, "cfi_idx", self.gen_params.fetch_width_log),
                        "cfi_type": self.candidate_cfi_type(m, pc, way),
                    }
                    for way in range(self.candidate_count)
                ]
            }

        @def_method(m, self.response_s2)
        def _():
            pc = s2_pipe.read(m).pc
            return {
                "candidates": [
                    {
                        "valid": self.candidate_field(pc, way, "valid", 1),
                        "cfi_idx": self.candidate_field(pc, way, "cfi_idx", self.gen_params.fetch_width_log),
                        "cfi_type": self.candidate_cfi_type(m, pc, way),
                        "target_valid": self.candidate_field(pc, way, "target_valid", 1),
                        "target": self.candidate_field(pc, way, "target", self.gen_params.isa.xlen),
                    }
                    for way in range(self.candidate_count)
                ],
                "meta": lookup(self.cases, pc, "meta", self.meta_width),
            }

        self.record_updates(m)

        return m


class MockDirectionPredictor(MockUpdateRecorder, DirectionPredictor):
    def __init__(self, gen_params: GenParams, cases: tuple[DirectionCase, ...]):
        super().__init__(gen_params, DIRECTION_META_WIDTH, CANDIDATE_COUNT)
        self.cases = cases

    def elaborate(self, platform):
        m = TModule()
        pc_layout = make_layout(("pc", self.gen_params.isa.xlen))
        m.submodules.s1_pipe = s1_pipe = Pipe(pc_layout)
        m.submodules.s2_pipe = s2_pipe = Pipe(pc_layout)

        @def_method(m, self.request_s0)
        def _(pc):
            s1_pipe.write(m, pc=pc)

        @def_method(m, self.accept_s1_hints)
        def _(pc, hints):
            requested_pc = s1_pipe.read(m).pc
            s2_pipe.write(m, pc=requested_pc)

        @def_method(m, self.response_s2)
        def _():
            pc = s2_pipe.read(m).pc
            return {
                "taken": lookup(self.cases, pc, "taken", self.gen_params.fetch_width),
                "meta": lookup(self.cases, pc, "meta", self.meta_width),
            }

        self.record_updates(m)

        return m


@dataclass(frozen=True)
class MockFastConfig(FastPredictorConfig):
    cases: tuple[FastCase, ...] = ()

    def meta_width(self, fetch_width: int) -> int:
        return FAST_META_WIDTH

    def get_module(self, gen_params: GenParams):
        return MockFastPredictor(gen_params, self.cases)


@dataclass(frozen=True)
class MockCfiConfig(CfiPredictorConfig):
    cases: tuple[CfiCase, ...] = ()

    def meta_width(self, fetch_width: int) -> int:
        return CFI_META_WIDTH

    def candidate_count(self) -> int:
        return CANDIDATE_COUNT

    def get_module(self, gen_params: GenParams):
        return MockCfiPredictor(gen_params, self.cases)


@dataclass(frozen=True)
class MockDirectionConfig(DirectionPredictorConfig):
    cases: tuple[DirectionCase, ...] = ()

    def meta_width(self, fetch_width: int) -> int:
        return DIRECTION_META_WIDTH

    def get_module(self, gen_params: GenParams):
        return MockDirectionPredictor(gen_params, self.cases)


@dataclass(frozen=True)
class Scenario:
    name: str
    fast: FastCase
    candidates: tuple[Candidate, ...]
    directions: int
    expected_s1_pc: int
    expected_s2_pc: int
    branch_mask: int
    cfi_idx: int = 0
    cfi_type: CfiType = CfiType.INVALID
    target_valid: int = 0


PC = 0x100
FALLTHROUGH = 0x110


SCENARIOS = [
    Scenario("both_miss", FastCase(PC), (), 0, FALLTHROUGH, FALLTHROUGH, 0),
    Scenario(
        "agree_taken",
        FastCase(PC, 1, 1, CfiType.BRANCH, 1, 0x280),
        (Candidate(1, 1, CfiType.BRANCH, 1, 0x280),),
        1 << 1,
        0x280,
        0x280,
        1 << 1,
        1,
        CfiType.BRANCH,
        1,
    ),
    Scenario(
        "fast_miss_backing_taken",
        FastCase(PC),
        (Candidate(1, 1, CfiType.BRANCH, 1, 0x280),),
        1 << 1,
        FALLTHROUGH,
        0x280,
        1 << 1,
        1,
        CfiType.BRANCH,
        1,
    ),
    Scenario(
        "fast_taken_backing_not_taken",
        FastCase(PC, 1, 1, CfiType.BRANCH, 1, 0x280),
        (Candidate(1, 1, CfiType.BRANCH, 1, 0x280),),
        0,
        0x280,
        FALLTHROUGH,
        1 << 1,
    ),
    Scenario(
        "same_cfi_different_target",
        FastCase(PC, 1, 1, CfiType.JALR, 1, 0x280),
        (Candidate(1, 1, CfiType.JALR, 1, 0x300),),
        0,
        0x280,
        0x300,
        0,
        1,
        CfiType.JALR,
        1,
    ),
    Scenario(
        "first_not_taken_second_taken",
        FastCase(PC),
        (
            Candidate(1, 1, CfiType.BRANCH, 1, 0x280),
            Candidate(1, 2, CfiType.BRANCH, 1, 0x300),
        ),
        1 << 2,
        FALLTHROUGH,
        0x300,
        (1 << 1) | (1 << 2),
        2,
        CfiType.BRANCH,
        1,
    ),
    Scenario(
        "unconditional_ignores_direction",
        FastCase(PC),
        (Candidate(1, 2, CfiType.JAL, 1, 0x300),),
        0,
        FALLTHROUGH,
        0x300,
        0,
        2,
        CfiType.JAL,
        1,
    ),
    Scenario(
        "earliest_taken_ignores_way_order",
        FastCase(PC),
        (
            Candidate(1, 3, CfiType.BRANCH, 1, 0x380),
            Candidate(1, 1, CfiType.BRANCH, 1, 0x280),
            Candidate(1, 2, CfiType.BRANCH, 1, 0x300),
        ),
        (1 << 1) | (1 << 2) | (1 << 3),
        FALLTHROUGH,
        0x280,
        (1 << 1) | (1 << 2) | (1 << 3),
        1,
        CfiType.BRANCH,
        1,
    ),
    Scenario(
        "same_slot_lower_way_wins",
        FastCase(PC),
        (
            Candidate(1, 2, CfiType.JAL, 1, 0x300),
            Candidate(1, 2, CfiType.JAL, 1, 0x380),
        ),
        0,
        FALLTHROUGH,
        0x300,
        0,
        2,
        CfiType.JAL,
        1,
    ),
    Scenario(
        "recognized_branch_without_target",
        FastCase(PC),
        (Candidate(1, 1, CfiType.BRANCH, 0, 0x280),),
        1 << 1,
        FALLTHROUGH,
        FALLTHROUGH,
        1 << 1,
    ),
]


class TestBranchPredictionUnit(TestCaseWithSimulator):
    @pytest.fixture(autouse=True)
    def setup(self, fixture_initialize_testing_env):
        DependencyContext.get().add_dependency(HwMetricsEnabledKey(), True)
        self.targets: deque[dict] = deque()
        self.details: deque[dict] = deque()

    @def_method_mock(lambda self: self.bpu.write_fetch_target)
    def write_fetch_target_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.targets.append({"pc": pc, "ftq_ptr": ftq_ptr, "correction": 0})

    @def_method_mock(lambda self: self.bpu.correct_fetch_target)
    def correct_fetch_target_mock(self, pc, ftq_ptr):
        @MethodMock.effect
        def eff():
            self.targets.append({"pc": pc, "ftq_ptr": ftq_ptr, "correction": 1})

    @def_method_mock(lambda self: self.bpu.write_prediction_details)
    def write_prediction_details_mock(self, ftq_ptr, pc, prediction, meta):
        @MethodMock.effect
        def eff():
            self.details.append(
                {
                    "ftq_ptr": ftq_ptr,
                    "pc": pc,
                    "prediction": prediction,
                    "meta": meta,
                }
            )

    def build(
        self,
        fast_cases: tuple[FastCase, ...] = (),
        cfi_cases: tuple[CfiCase, ...] | None = (),
        direction_cases: tuple[DirectionCase, ...] | None = (),
    ):
        config = BranchPredictionConfig(
            fast_predictor=MockFastConfig(fast_cases),
            cfi_predictor=None if cfi_cases is None else MockCfiConfig(cfi_cases),
            direction_predictor=(None if direction_cases is None else MockDirectionConfig(direction_cases)),
        )
        self.gen_params = GenParams(configurations.test.replace(fetch_block_bytes_log=4, bpu_config=config))
        self.dut = BranchPredictionUnit(self.gen_params)
        self.bpu = SimpleTestCircuit(self.dut)

    async def predict(self, sim: TestbenchContext, pc: int, ftq_ptr: int = 0):
        self.targets.clear()
        self.details.clear()
        await self.bpu.request.call(sim, pc=pc, ftq_ptr={"ptr": ftq_ptr, "parity": 0})
        for _ in range(12):
            if self.details:
                break
            await sim.tick()
        assert self.details
        for _ in range(3):
            await sim.tick()
        return list(self.targets), self.details[-1]

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
    def test_composition_scenarios(self, scenario: Scenario):
        fast = FastCase(**{**scenario.fast.__dict__, "meta": 0xA})
        cfi = CfiCase(PC, scenario.candidates, meta=0x5C)
        direction = DirectionCase(PC, scenario.directions, meta=0xD3)
        self.build((fast,), (cfi,), (direction,))

        async def proc(sim: TestbenchContext):
            targets, details = await self.predict(sim, PC, ftq_ptr=3)
            expected_targets = [
                {
                    "pc": scenario.expected_s1_pc,
                    "ftq_ptr": {"ptr": 3, "parity": 0},
                    "correction": 0,
                }
            ]
            if scenario.expected_s1_pc != scenario.expected_s2_pc:
                expected_targets.append(
                    {
                        "pc": scenario.expected_s2_pc,
                        "ftq_ptr": {"ptr": 3, "parity": 0},
                        "correction": 1,
                    }
                )
            assert targets == expected_targets

            prediction = details["prediction"]
            assert details["ftq_ptr"] == {"ptr": 3, "parity": 0}
            assert details["pc"] == PC
            assert prediction["branch_mask"] == scenario.branch_mask
            assert prediction["cfi_idx"] == scenario.cfi_idx
            assert prediction["cfi_type"] == scenario.cfi_type
            assert prediction["cfi_target"] == (scenario.expected_s2_pc if scenario.target_valid else 0)
            assert prediction["cfi_target_valid"] == scenario.target_valid
            assert details["meta"] == 0xA | (0x5C << FAST_META_WIDTH) | (0xD3 << (FAST_META_WIDTH + CFI_META_WIDTH))

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_mid_block_entry_filters_older_candidates(self):
        pc = 0x108
        self.build(
            (FastCase(pc, 1, 1, CfiType.JAL, 1, 0x240),),
            (
                CfiCase(
                    pc,
                    (
                        Candidate(1, 1, CfiType.JAL, 1, 0x240),
                        Candidate(1, 3, CfiType.JAL, 1, 0x340),
                    ),
                ),
            ),
            (DirectionCase(pc),),
        )

        async def proc(sim: TestbenchContext):
            targets, details = await self.predict(sim, pc)
            assert targets == [
                {
                    "pc": FALLTHROUGH,
                    "ftq_ptr": {"ptr": 0, "parity": 0},
                    "correction": 0,
                },
                {"pc": 0x340, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 1},
            ]
            assert details["prediction"]["cfi_idx"] == 3

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_fast_only_hit_and_miss(self):
        hit_pc = 0x100
        miss_pc = 0x200
        self.build(
            (FastCase(hit_pc, 1, 1, CfiType.BRANCH, 1, 0x280, meta=0xB),),
            cfi_cases=None,
            direction_cases=None,
        )

        async def proc(sim: TestbenchContext):
            targets, details = await self.predict(sim, hit_pc)
            assert targets == [{"pc": 0x280, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 0}]
            assert details["prediction"] == {
                "branch_mask": 1 << 1,
                "cfi_idx": 1,
                "cfi_type": CfiType.BRANCH,
                "cfi_target": 0x280,
                "cfi_target_valid": 1,
            }
            assert details["meta"] == 0xB

            targets, details = await self.predict(sim, miss_pc, ftq_ptr=1)
            assert targets == [{"pc": 0x210, "ftq_ptr": {"ptr": 1, "parity": 0}, "correction": 0}]
            assert details["prediction"]["cfi_target_valid"] == 0
            assert details["prediction"]["branch_mask"] == 0

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_fast_predictor_miss_without_backing_predictors_falls_through(self):
        self.build(fast_cases=(), cfi_cases=None, direction_cases=None)

        async def proc(sim: TestbenchContext):
            targets, details = await self.predict(sim, PC, ftq_ptr=2)
            assert targets == [{"pc": FALLTHROUGH, "ftq_ptr": {"ptr": 2, "parity": 0}, "correction": 0}]
            assert details["prediction"] == {
                "branch_mask": 0,
                "cfi_idx": 0,
                "cfi_type": CfiType.INVALID,
                "cfi_target": 0,
                "cfi_target_valid": 0,
            }
            assert details["meta"] == 0

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_backing_predictors_work_when_fast_predictor_misses(self):
        target = 0x2C0
        self.build(
            fast_cases=(),
            cfi_cases=(CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, target),), meta=0x5C),),
            direction_cases=(DirectionCase(PC, meta=0xD3),),
        )

        async def proc(sim: TestbenchContext):
            targets, details = await self.predict(sim, PC)
            assert targets == [
                {"pc": FALLTHROUGH, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 0},
                {"pc": target, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 1},
            ]
            assert details["prediction"]["cfi_target"] == target
            assert details["meta"] == (0x5C << FAST_META_WIDTH) | (0xD3 << (FAST_META_WIDTH + CFI_META_WIDTH))

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_back_to_back_requests_keep_context_and_metadata_aligned(self):
        first_pc, second_pc = 0x100, 0x200
        first_target, second_target = 0x280, 0x380
        self.build(
            (
                FastCase(first_pc, 1, 1, CfiType.JAL, 1, first_target, meta=1),
                FastCase(second_pc, 1, 2, CfiType.JAL, 1, second_target, meta=2),
            ),
            (
                CfiCase(first_pc, (Candidate(1, 1, CfiType.JAL, 1, first_target),), meta=3),
                CfiCase(second_pc, (Candidate(1, 2, CfiType.JAL, 1, second_target),), meta=4),
            ),
            (DirectionCase(first_pc, meta=5), DirectionCase(second_pc, meta=6)),
        )

        async def proc(sim: TestbenchContext):
            await self.bpu.request.call(sim, pc=first_pc, ftq_ptr={"ptr": 2, "parity": 0})
            await self.bpu.request.call(sim, pc=second_pc, ftq_ptr={"ptr": 3, "parity": 0})
            for _ in range(12):
                if len(self.details) == 2 and len(self.targets) == 2:
                    break
                await sim.tick()

            assert [(target["ftq_ptr"]["ptr"], target["pc"]) for target in self.targets] == [
                (2, first_target),
                (3, second_target),
            ]
            assert [(detail["ftq_ptr"]["ptr"], detail["prediction"]["cfi_target"]) for detail in self.details] == [
                (2, first_target),
                (3, second_target),
            ]
            assert [detail["meta"] for detail in self.details] == [
                1 | (3 << FAST_META_WIDTH) | (5 << (FAST_META_WIDTH + CFI_META_WIDTH)),
                2 | (4 << FAST_META_WIDTH) | (6 << (FAST_META_WIDTH + CFI_META_WIDTH)),
            ]

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_flush_discards_pending_request(self):
        self.build(
            (FastCase(PC, 1, 1, CfiType.JAL, 1, 0x280),),
            (CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, 0x280),)),),
            (DirectionCase(PC),),
        )

        async def proc(sim: TestbenchContext):
            await self.bpu.request.call(sim, pc=PC, ftq_ptr={"ptr": 0, "parity": 0})
            await self.bpu.flush.call(sim)
            for _ in range(5):
                await sim.tick()
            assert not self.targets
            assert not self.details

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("cycles_before_flush", range(4))
    def test_flush_discards_request_at_each_pipeline_stage(self, cycles_before_flush: int):
        self.build(
            (FastCase(PC, 0, 0, CfiType.INVALID, 0, 0),),
            (CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, 0x280),)),),
            (DirectionCase(PC),),
        )

        async def proc(sim: TestbenchContext):
            await self.bpu.request.call(sim, pc=PC, ftq_ptr={"ptr": 7, "parity": 0})
            for _ in range(cycles_before_flush):
                await sim.tick()
            await self.bpu.flush.call(sim)
            self.targets.clear()
            self.details.clear()
            for _ in range(5):
                await sim.tick()
            assert not self.targets
            assert not self.details

            # The flushed lookup was still read out of the predictors, so the next one gets
            # its own results.
            targets, details = await self.predict(sim, PC, ftq_ptr=8)
            assert targets == [
                {"pc": FALLTHROUGH, "ftq_ptr": {"ptr": 8, "parity": 0}, "correction": 0},
                {"pc": 0x280, "ftq_ptr": {"ptr": 8, "parity": 0}, "correction": 1},
            ]
            assert details["ftq_ptr"] == {"ptr": 8, "parity": 0}

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_flush_discards_request_made_in_the_same_cycle(self):
        self.build(
            (FastCase(PC, 1, 1, CfiType.JAL, 1, 0x280),),
            (CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, 0x280),)),),
            (DirectionCase(PC),),
        )

        async def proc(sim: TestbenchContext):
            await (
                CallTrigger(sim)
                .call(self.bpu.request, pc=PC, ftq_ptr={"ptr": 0, "parity": 0})
                .call(self.bpu.flush)
                .until_all_done()
            )
            for _ in range(5):
                await sim.tick()
            assert not self.targets
            assert not self.details

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_s2_correction_overrides_younger_s1_and_discards_its_metadata(self):
        younger_pc, corrected_pc = 0x200, 0x300
        self.build(
            (
                FastCase(PC, 1, 1, CfiType.JAL, 1, younger_pc, meta=1),
                FastCase(younger_pc, 1, 1, CfiType.JAL, 1, 0x400, meta=2),
                FastCase(corrected_pc, meta=3),
            ),
            (CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, corrected_pc),), meta=0x5C),),
            (DirectionCase(PC, meta=0xD3),),
        )

        async def proc(sim: TestbenchContext):
            await self.bpu.request.call(sim, pc=PC, ftq_ptr={"ptr": 0, "parity": 0})
            await self.bpu.request.call(sim, pc=younger_pc, ftq_ptr={"ptr": 1, "parity": 0})
            for _ in range(6):
                await sim.tick()
            # S1 still passes on the younger request's target in the correction cycle; the
            # FAU lets the correction override it.
            assert [target for target in self.targets if not target["correction"]] == [
                {"pc": younger_pc, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 0},
                {"pc": 0x400, "ftq_ptr": {"ptr": 1, "parity": 0}, "correction": 0},
            ]
            assert [target for target in self.targets if target["correction"]] == [
                {"pc": corrected_pc, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 1},
            ]
            assert [detail["pc"] for detail in self.details] == [PC]
            assert self.details[0]["meta"] == 1 | (0x5C << FAST_META_WIDTH) | (
                0xD3 << (FAST_META_WIDTH + CFI_META_WIDTH)
            )

            # Reusing the squashed slot must produce the new request's metadata.
            targets, details = await self.predict(sim, corrected_pc, ftq_ptr=1)
            assert targets == [{"pc": 0x310, "ftq_ptr": {"ptr": 1, "parity": 0}, "correction": 0}]
            assert details["pc"] == corrected_pc
            assert details["meta"] == 3

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    def test_request_in_correction_cycle_survives(self):
        # The FTQ holds allocation back while S2 corrects, but nothing in the BPU may rely on
        # that: a request made in the correction cycle is on the corrected path.
        younger_pc, corrected_pc = 0x200, 0x300
        self.build(
            (
                FastCase(PC, 1, 1, CfiType.JAL, 1, younger_pc, meta=1),
                FastCase(younger_pc, 1, 1, CfiType.JAL, 1, 0x400, meta=2),
                FastCase(corrected_pc, meta=3),
            ),
            (CfiCase(PC, (Candidate(1, 1, CfiType.JAL, 1, corrected_pc),), meta=0x5C),),
            (DirectionCase(PC, meta=0xD3),),
        )

        async def proc(sim: TestbenchContext):
            await self.bpu.request.call(sim, pc=PC, ftq_ptr={"ptr": 0, "parity": 0})
            await self.bpu.request.call(sim, pc=younger_pc, ftq_ptr={"ptr": 1, "parity": 0})
            await self.bpu.request.call(sim, pc=corrected_pc, ftq_ptr={"ptr": 1, "parity": 1})
            for _ in range(6):
                await sim.tick()

            assert [target for target in self.targets if target["correction"]] == [
                {"pc": corrected_pc, "ftq_ptr": {"ptr": 0, "parity": 0}, "correction": 1},
            ]
            # The correction came in the cycle the third request was made...
            assert self.targets[-1] == {"pc": 0x310, "ftq_ptr": {"ptr": 1, "parity": 1}, "correction": 0}
            # ...and only the younger request it squashed is missing from the details.
            assert [(detail["ftq_ptr"], detail["pc"], detail["meta"]) for detail in self.details] == [
                (
                    {"ptr": 0, "parity": 0},
                    PC,
                    1 | (0x5C << FAST_META_WIDTH) | (0xD3 << (FAST_META_WIDTH + CFI_META_WIDTH)),
                ),
                ({"ptr": 1, "parity": 1}, corrected_pc, 3),
            ]

        with self.run_simulation(self.bpu) as sim:
            sim.add_testbench(proc)

    @pytest.mark.parametrize("backing_enabled", [False, True])
    def test_prediction_metadata_round_trips_to_each_predictor(self, backing_enabled):
        self.build(
            (FastCase(PC, meta=0xA),),
            (CfiCase(PC, meta=0x5C),) if backing_enabled else None,
            (DirectionCase(PC, meta=0xD3),) if backing_enabled else None,
        )
        configs = self.gen_params.bpu_config.components()
        predictors = [config.get_module(self.gen_params) for config in configs]

        async def proc(sim: TestbenchContext):
            _, details = await self.predict(sim, PC)
            update = dict(
                pc=details["pc"],
                branch_mask=0b1010,
                cfi_target=0x340,
                cfi_idx=3,
                cfi_type=CfiType.BRANCH,
                taken=1,
                mispredict=1,
            )
            await self.bpu.update.call(sim, **update, meta=details["meta"])
            for predictor, expected_meta in zip(predictors, (0xA, 0x5C, 0xD3)):
                assert isinstance(predictor, MockUpdateRecorder)
                assert sim.get(predictor.update_count) == 1
                for field, value in update.items():
                    assert sim.get(getattr(predictor.last_update, field)) == value
                assert sim.get(predictor.last_update.meta) == expected_meta

        # Hack: the BPU builds its predictors itself during elaboration, so make each config
        # hand it the instance built above, whose signals the testbench can then inspect.
        with ExitStack() as stack:
            for config, predictor in zip(configs, predictors):
                stack.enter_context(patch.object(type(config), "get_module", return_value=predictor))
            with self.run_simulation(self.bpu) as sim:
                sim.add_testbench(proc)
