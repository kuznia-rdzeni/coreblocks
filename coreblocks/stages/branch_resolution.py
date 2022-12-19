from amaranth import *

from coreblocks.params import GenParams
from coreblocks.transactions import Method, Transaction


class BranchResolution(Elaboratable):
    def __init__(self, *, gen_params: GenParams, get_branch_result: Method, branch_verify: Method):
        self.gen_params = gen_params
        self.get_branch_result = get_branch_result
        self.branch_verify = branch_verify

    def elaborate(self, platform):
        m = Module()

        with Transaction().body(m):
            branch = self.get_branch_result(m)

            with m.If(branch.taken):
                self.branch_verify(m, {"next_pc": branch.jmp_addr})
            with m.Else():
                self.branch_verify(m, {"next_pc": branch.next_addr})

        return m
