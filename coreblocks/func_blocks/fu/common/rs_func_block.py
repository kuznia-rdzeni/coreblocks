from collections.abc import Collection, Iterable, Sequence
from amaranth import *
from dataclasses import dataclass
from coreblocks.params import *
from .rs import RS, RSBase
from coreblocks.scheduler.wakeup_select import WakeupSelect
from transactron import Method, Methods, TModule, def_method
from transactron.evlog import EventSource
from coreblocks.func_blocks.interface.func_protocols import FuncUnit, FuncBlock
from transactron.lib import BasicFifo, ConnectTrans, Forwarder
from transactron.utils import MethodStruct, OneHotSwitchDynamic
from coreblocks.arch import OpType
from coreblocks.interface.layouts import RSInterfaceLayouts, RSLayouts, FuncUnitLayouts
from coreblocks.telemetry import FuIssue, func_unit_kind

__all__ = ["RSFuncBlock", "RSBlockComponent"]


evlog = EventSource("backend.rs_func_block")


def _issue_to_group(m: TModule, func_units: Iterable[tuple[FuncUnit, set[OpType]]], arg: MethodStruct):
    func_units = list(func_units)
    all_optypes: set[OpType] = set()
    for _, unit_optypes in func_units:
        if all_optypes & unit_optypes:
            raise ValueError(f"OpTypes handled by multiple grouped units: {all_optypes & unit_optypes}")
        all_optypes |= unit_optypes

    unit_select = Signal(len(func_units))
    m.d.av_comb += unit_select.eq(
        Cat(Cat(arg.exec_fn.op_type == optype for optype in unit_optypes).any() for _, unit_optypes in func_units)
    )

    for n in OneHotSwitchDynamic(m, unit_select):
        func_units[n][0].issue(m, arg)

    for n, (func_unit, _) in enumerate(func_units):
        evlog.emit(m, FuIssue.hw(rob_id=arg.rob_id, unit=func_unit_kind(func_unit)), when=unit_select[n])


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
    update: Methods
        RS update methods.
    get_result: Method
        Method used for getting single result out of one of the FUs. It uses
        layout described by `FuncUnitLayouts`.
    """

    def __init__(
        self,
        gen_params: GenParams,
        func_unit_groups: Iterable[Sequence[tuple[FuncUnit, set[OpType], bool]]],
        rs_entries: int,
        rs_number: int,
        rs_type: type[RSBase],
    ):
        """
        Parameters
        ----------
        gen_params: GenParams
            Core generation parameters.
        func_unit_groups: Iterable[Sequence[tuple[FuncUnit, set[OpType], bool]]]
            Groups of functional units to be used by this module, with the `OpType`\\s handled
            by each unit, and whether the unit's results are buffered in a FIFO. The units in
            a group share a single wakeup-select unit. Grouped units should always be ready,
            otherwise a busy unit blocks issuing to the whole group.
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
        self.rs_number = rs_number
        self.rs_layouts = gen_params.get(RSLayouts, rs_entries=rs_entries)
        self.fu_layouts = gen_params.get(FuncUnitLayouts)
        self.func_unit_groups = [list(group) for group in func_unit_groups]

        self.insert = Method(i=self.rs_layouts.rs.insert_in)
        self.select = Method(o=self.rs_layouts.rs.select_out)
        self.update = Methods(gen_params.announcement_superscalarity, i=self.rs_layouts.rs.update_in)
        self.get_result = Method(o=self.fu_layouts.push_result)

    def elaborate(self, platform):
        m = TModule()

        m.submodules.rs = self.rs = self.rs_type(
            gen_params=self.gen_params,
            rs_entries=self.rs_entries,
            rs_number=self.rs_number,
            rs_ways=self.gen_params.announcement_superscalarity,
            ready_for=(set().union(*(optypes for _, optypes, _ in group)) for group in self.func_unit_groups),
        )

        m.submodules.forwarder = forwarder = Forwarder(self.fu_layouts.push_result)

        for n, group in enumerate(self.func_unit_groups):
            for k, (func_unit, _optypes, result_fifo) in enumerate(group):
                suffix = f"{n}" if len(group) == 1 else f"{n}_{k}"
                if result_fifo:
                    result_fifo_unit = BasicFifo(self.fu_layouts.push_result, 2)
                    m.submodules[f"result_fifo_{suffix}"] = result_fifo_unit
                    m.submodules[f"result_connect_{suffix}"] = ConnectTrans.create(
                        result_fifo_unit.read, forwarder.write
                    )
                    func_unit.push_result.provide(result_fifo_unit.write)
                else:
                    func_unit.push_result.provide(forwarder.write)
                m.submodules[f"func_unit_{suffix}"] = func_unit

            wakeup_select = WakeupSelect(
                gen_params=self.gen_params,
                rs_entries=self.rs_entries,
                # issue events of grouped units are reported by `issue_to_group`
                fu_kind=func_unit_kind(group[0][0]) if len(group) == 1 else None,
            )
            m.submodules[f"wakeup_select_{n}"] = wakeup_select
            wakeup_select.get_ready.provide(self.rs.get_ready_list[n])
            wakeup_select.take_row.provide(self.rs.take)
            if len(group) == 1:
                wakeup_select.issue.provide(group[0][0].issue)
            else:
                # provide implementation by defining it directly
                @def_method(m, wakeup_select.issue)
                def _(arg):
                    _issue_to_group(m, [(func_unit, optypes) for func_unit, optypes, _ in group], arg)

        self.insert.provide(self.rs.insert)
        self.select.provide(self.rs.select)
        self.update.provide(self.rs.update)
        self.get_result.provide(forwarder.read)

        return m


@dataclass(frozen=True)
class RSBlockComponent(BlockComponentParams):
    func_units: Collection[FunctionalComponentParams | FuncUnitGroup]
    rs_entries: int
    rs_number: int = -1  # overwritten by CoreConfiguration
    rs_type: type[RSBase] = RS

    def get_module(self, gen_params: GenParams) -> FuncBlock:
        func_unit_groups = [
            entry.func_units if isinstance(entry, FuncUnitGroup) else (entry,) for entry in self.func_units
        ]

        rs_unit = RSFuncBlock(
            gen_params=gen_params,
            func_unit_groups=[
                [(unit.get_module(gen_params), unit.get_optypes(), unit.result_fifo) for unit in group]
                for group in func_unit_groups
            ],
            rs_entries=self.rs_entries,
            rs_number=self.rs_number,
            rs_type=self.rs_type,
        )
        return rs_unit

    def get_optypes(self) -> set[OpType]:
        return optypes_supported(self.func_units)

    def get_layouts(self, gen_params: GenParams) -> RSInterfaceLayouts:
        return gen_params.get(RSLayouts, rs_entries=self.rs_entries).rs

    def get_rs_entry_count(self) -> int:
        return self.rs_entries
