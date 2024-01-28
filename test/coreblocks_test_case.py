from .common import TestCaseWithSimulator
from coreblocks.params import GenParams


__all__ = ["CoreblocksTestCaseWithSimulator"]


class CoreblocksTestCaseWithSimulator(TestCaseWithSimulator):
    gen_params: GenParams

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def dependency_manager(self):
        return self.gen_params
