import random
import pytest
from amaranth.lib.enum import auto
from collections import deque
from enum import Enum

from coreblocks.arch import OpType
from coreblocks.func_blocks.fu.common.rs_func_block import RSBlockComponent
from coreblocks.params import GenParams
from coreblocks.params.configurations import test_core_config
from transactron.testing import CallTrigger, MethodMock, TestCaseWithSimulator, def_method_mock

from test.scheduler.test_scheduler import SchedulerTestCircuit


class TestSchedulerCheckpointing(TestCaseWithSimulator):
    @pytest.mark.parametrize("tag_bits, checkpoint_count", [(2, 3), (5, 8)])
    def test_randomized(self, tag_bits: int, checkpoint_count: int):
        gen_params = GenParams(
            test_core_config.replace(
                func_units_config=(
                    RSBlockComponent([], rs_entries=4, rs_number=0),
                    RSBlockComponent([], rs_entries=4, rs_number=1),
                ),
                tag_bits=tag_bits,
                checkpoint_count=checkpoint_count,
            )
        )

        rs = [{OpType.ARITHMETIC}, {OpType.BRANCH}]
        dut = SchedulerTestCircuit(gen_params, rs)

        branch_in_flight = set()

        instr_cnt = 512
        exp_rs_branch = deque()
        exp_rs_arith = deque()

        correct_path_id = 0
        wrong_path_id = 0x8000
        on_correct_path = True
        free_rp = 1
        frat_to_restore = []

        rollback_tag = 0
        rollback_tag_v = False

        random.seed(42)

        end = False

        class BranchEncoding(Enum):
            CORRECT_PATH_OK = auto()
            CORRECT_PATH_MISPRED_EXIT = auto()
            WRONG_PATH_OK = auto()
            WRONG_PATH_WITH_ROLLBACK = auto()

        in_order_branch_encoding = deque()
        in_order_arith_encoding = deque()
        frat = [0 for _ in range(2**gen_params.isa.reg_cnt_log)]

        def get_instr():
            nonlocal correct_path_id, wrong_path_id, on_correct_path, free_rp, frat, frat_to_restore, rollback_tag
            nonlocal rollback_tag_v
            is_branch = random.randint(0, 1)

            rd = random.randrange(0, 4)
            rs = random.randrange(0, 4)
            instr = {
                "exec_fn": {"op_type": OpType.BRANCH if is_branch else OpType.ARITHMETIC},
                "imm": correct_path_id if on_correct_path else wrong_path_id,
                "regs_l": {
                    "rl_dst": rd,
                    "rl_s1": rs,
                },
                "rollback_tag": rollback_tag,
                "rollback_tag_v": rollback_tag_v,
                "commit_checkpoint": is_branch,
            }
            rollback_tag_v = False

            if on_correct_path:
                if is_branch:
                    exp_rs_branch.append(frat[rs])
                else:
                    exp_rs_arith.append(frat[rs])
                correct_path_id += 1
            else:
                wrong_path_id += 1

            if rd != 0:
                frat[rd] = free_rp
                free_rp += 1
                if free_rp == gen_params.phys_regs:
                    free_rp = 1

            if is_branch:
                is_misprediction = random.randint(0, 1)
                if on_correct_path:
                    in_order_branch_encoding.append(
                        BranchEncoding.CORRECT_PATH_MISPRED_EXIT if is_misprediction else BranchEncoding.CORRECT_PATH_OK
                    )
                    if is_misprediction:
                        on_correct_path = False
                        frat_to_restore = frat.copy()
                else:
                    in_order_branch_encoding.append(
                        BranchEncoding.WRONG_PATH_WITH_ROLLBACK if is_misprediction else BranchEncoding.WRONG_PATH_OK
                    )
            else:
                in_order_arith_encoding.append(on_correct_path)

            return instr

        async def input_process(sim):
            nonlocal end
            for _ in range(instr_cnt):
                data = get_instr()
                await dut.instr_inp.call(sim, data)
                await self.random_wait_geom(sim, 0.5)
            end = True

        rob_id_to_imm_id = {}

        async def free_rf_process(sim):
            free_rp_inp = 1
            while True:
                await dut.free_rf_inp.call(sim, {"reg_id": free_rp_inp})
                free_rp_inp += 1
                if free_rp_inp == gen_params.phys_regs:
                    free_rp_inp = 1

        retire_imm_ids = 0
        current_tag = 0

        async def rob_retire_process(sim):
            nonlocal current_tag, retire_imm_ids, end
            for _ in range(instr_cnt):
                await self.random_wait_geom(sim, 0.4)

                _, active_tags, entry, rob_idxs = (
                    await CallTrigger(sim)
                    .call(dut.rob_retire)
                    .call(dut.get_active_tags)
                    .call(dut.rob_peek)
                    .call(dut.rob_get_indices)
                    .until_all_done()
                )
                active_tags = active_tags["active_tags"]
                entry = entry["rob_data"]
                rob_id = rob_idxs["start"]

                current_tag += entry["tag_increment"]
                current_tag %= 2**gen_params.tag_bits

                if active_tags[current_tag]:
                    # check for instructions on vaild speculation path retiring in order
                    assert rob_id_to_imm_id[rob_id] == retire_imm_ids
                    retire_imm_ids += 1

                if entry["tag_increment"]:
                    await dut.free_tag.call(sim)

        @def_method_mock(lambda: dut.core_state)
        def core_state_mock():
            return {"flushing": 0}

        @def_method_mock(lambda: dut.rs_alloc[0], enable=lambda: random.random() < 0.9)
        def rs_alloc_arith():
            return {"rs_entry_id": 0}

        @def_method_mock(lambda: dut.rs_alloc[1], enable=lambda: random.random() < 0.9)
        def rs_alloc_branch():
            return {"rs_entry_id": 0}

        @def_method_mock(lambda: dut.rs_insert[1])
        def rs_insert_branch(arg):
            nonlocal rob_id_to_imm_id

            @MethodMock.effect
            def _():
                nonlocal arg
                arg = arg["rs_data"]
                rob_id_to_imm_id[arg["rob_id"]] = arg["imm"]

                br_on_correct_path = (
                    in_order_branch_encoding[0] == BranchEncoding.CORRECT_PATH_OK
                    or in_order_branch_encoding[0] == BranchEncoding.CORRECT_PATH_MISPRED_EXIT
                )
                if br_on_correct_path:
                    assert arg["rp_s1"] == exp_rs_branch[0]
                    exp_rs_branch.popleft()

                br = {
                    "encoding": in_order_branch_encoding[0],
                    "rob_id": arg["rob_id"],
                    "tag": arg["tag"],
                }

                in_order_branch_encoding.popleft()
                branch_in_flight.add(frozenset(br.items()))

        rob_done_queue = deque()

        async def rs_insert_arithmetic(sim):
            while True:
                nonlocal rob_id_to_imm_id
                arg = None
                while arg is None:
                    await self.random_wait_geom(sim, 0.5)
                    arg = await dut.rs_insert[0].call_try(sim)
                arg = arg["rs_data"]

                rob_id_to_imm_id[arg["rob_id"]] = arg["imm"]

                if in_order_arith_encoding[0]:
                    assert arg["rp_s1"] == exp_rs_arith[0]
                    exp_rs_arith.popleft()

                in_order_arith_encoding.popleft()
                rob_done_queue.append(arg["rob_id"])

        async def active_tags_call_process(sim):
            while True:
                await dut.get_active_tags.call(sim)

        async def branch_fu_process(sim):
            nonlocal on_correct_path, frat, rollback_tag, rollback_tag_v, frat_to_restore

            while True:
                await self.random_wait_geom(sim, 0.5)
                if not branch_in_flight:
                    continue
                instr = random.choice(tuple(branch_in_flight))
                branch_in_flight.remove(instr)
                instr = dict(instr)

                await sim.delay(1e-9)

                active_tags_val = dut.get_active_tags.get_outputs(sim)["active_tags"]
                wrong_path_rollback_legal = instr["encoding"] == BranchEncoding.WRONG_PATH_WITH_ROLLBACK and (
                    active_tags_val[instr["tag"]]
                )

                if wrong_path_rollback_legal or instr["encoding"] == BranchEncoding.CORRECT_PATH_MISPRED_EXIT:
                    await dut.rollback.call(sim, tag=instr["tag"])
                    rollback_tag = instr["tag"]
                    rollback_tag_v = True
                    if instr["encoding"] == BranchEncoding.CORRECT_PATH_MISPRED_EXIT:
                        frat = frat_to_restore.copy()
                        on_correct_path = True

                rob_done_queue.append(instr["rob_id"])

        async def mark_done_process(sim):
            while True:
                while not rob_done_queue:
                    await sim.tick()
                await dut.rob_done.call(sim, rob_id=rob_done_queue[0])
                rob_done_queue.popleft()

        with self.run_simulation(dut, max_cycles=2000) as sim:
            sim.add_testbench(input_process)
            sim.add_testbench(free_rf_process, background=True)
            sim.add_testbench(branch_fu_process, background=True)
            sim.add_testbench(rs_insert_arithmetic, background=True)
            sim.add_testbench(mark_done_process, background=True)
            sim.add_testbench(active_tags_call_process, background=True)
            sim.add_testbench(rob_retire_process)
