from typing import Protocol
from transactron import Method, Provided, Required
from transactron.utils._typing import HasElaborate
from coreblocks.params import GenParams
from coreblocks.interface.layouts import FuncUnitLayouts

__all__ = ["FuncUnit", "FuncBlock"]


class FuncUnit(HasElaborate, Protocol):
    issue: Provided[Method]
    push_result: Required[Method]

    # TODO move this to another class, and
    # make all but JumpBranchWrapper inherit from it instead
    gen_params: Required[GenParams]
    layouts: Required[FuncUnitLayouts]

    def __init__(self, gen_params: GenParams):
        self.gen_params = gen_params
        self.layouts = gen_params.get(FuncUnitLayouts)
        self.issue = Method(i=self.layouts.issue)
        self.push_result = Method(i=self.layouts.push_result)


class FuncBlock(HasElaborate, Protocol):
    insert: Method
    select: Method
    update: Method
    get_result: Method
