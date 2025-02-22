from collections.abc import Collection, Iterable
from amaranth import *
from dataclasses import dataclass
from coreblocks.params import *
from .rs import RS, RSBase
from coreblocks.scheduler.wakeup_select import WakeupSelect
from transactron import Method, TModule
from coreblocks.func_blocks.interface.func_protocols import FuncUnit, FuncBlock
from transactron.lib import FIFO, Collector, Connect
from coreblocks.arch import OpType
from coreblocks.interface.layouts import RSLayouts, FuncUnitLayouts

__all__ = ["RSFuncBlock", "RSBlockComponent"]


class RSFuncBlock(FuncBlock, Elaboratable):
    """
    Module combining multiple functional units with single RS unit. With
    input interface of RS and output interface of single FU.

    Attributes
    ----------
    insert: Method
        RS insert method.
    select: Method
        RS select method.
    update: Method
        RS update method.
    get_result: Method
        Method used for getting single result out of one of the FUs. It uses
        layout described by `FuncUnitLayouts`.
    """

    def __init__(
        self,
        gen_params: GenParams,
        func_units: Iterable[tuple[FuncUnit, set[OpType], bool]],
        rs_entries: int,
        rs_number: int,
        rs_type: type[RSBase],
    ):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        func_units: Iterable[FuncUnit]
            Functional units to be used by this module.
        rs_entries: int
            Number of entries in RS.
        rs_number: int
            The number of this RS block. Used for debugging.
        rs_type: type[RSBase]
            The RS type to use.
        """
        self.gen_params = gen_params
        self.rs_entries = rs_entries
        self.rs_type = rs_type
        self.rs_entries_bits = (rs_entries - 1).bit_length()
        self.rs_number = rs_number
        self.rs_layouts = gen_params.get(RSLayouts, rs_entries_bits=self.rs_entries_bits)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_units = list(func_units)

        self.insert = Method(i=self.rs_layouts.rs.insert_in)
        self.select = Method(o=self.rs_layouts.rs.select_out)
        self.update = Method(i=self.rs_layouts.rs.update_in)
        self.get_result = Method(o=self.fu_layouts.push_result)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rs = self.rs = self.rs_type(
            gen_params=self.gen_params,
            rs_entries=self.rs_entries,
            rs_number=self.rs_number,
            ready_for=(optypes for _, optypes, _ in self.func_units),
        )

        targets: list[Method] = []

        for n, (func_unit, _, result_fifo) in enumerate(self.func_units):
            wakeup_select = WakeupSelect(
                gen_params=self.gen_params,
                rs_entries_bits=self.rs_entries_bits,
            )
            wakeup_select.get_ready.proxy(m, self.rs.get_ready_list[n])
            wakeup_select.take_row.proxy(m, self.rs.take)
            wakeup_select.issue.proxy(m, func_unit.issue)
            if result_fifo:
                connector = FIFO(self.gen_params.get(FuncUnitLayouts).push_result, 2)
            else:
                connector = Connect(self.gen_params.get(FuncUnitLayouts).push_result)
            m.submodules[f"func_unit_{n}"] = func_unit
            m.submodules[f"wakeup_select_{n}"] = wakeup_select
            m.submodules[f"connector_{n}"] = connector
            func_unit.push_result.proxy(m, connector.write)
            targets.append(connector.read)

        m.submodules.collector = collector = Collector(targets)

        self.insert.proxy(m, self.rs.insert)
        self.select.proxy(m, self.rs.select)
        self.update.proxy(m, self.rs.update)
        self.get_result.proxy(m, collector.method)

        return m


@dataclass(frozen=True)
class RSBlockComponent(BlockComponentParams):
    func_units: Collection[FunctionalComponentParams]
    rs_entries: int
    rs_number: int = -1  # overwritten by CoreConfiguration
    rs_type: type[RSBase] = RS

    def get_module(self, gen_params: GenParams) -> FuncBlock:
        modules = list((u.get_module(gen_params), u.get_optypes(), u.result_fifo) for u in self.func_units)
        rs_unit = RSFuncBlock(
            gen_params=gen_params,
            func_units=modules,
            rs_entries=self.rs_entries,
            rs_number=self.rs_number,
            rs_type=self.rs_type,
        )
        return rs_unit

    def get_optypes(self) -> set[OpType]:
        return optypes_supported(self.func_units)

    def get_rs_entry_count(self) -> int:
        return self.rs_entries
