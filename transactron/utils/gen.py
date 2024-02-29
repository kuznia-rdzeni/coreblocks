from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from amaranth import *
from amaranth.back import verilog
from amaranth.hdl import ir
from amaranth.hdl.ast import SignalDict

from transactron.core import TransactionManager, MethodMap, TransactionManagerKey
from transactron.lib.metrics import HardwareMetricsManager
from transactron.utils.dependencies import DependencyContext
from transactron.utils.idgen import IdGenerator
from transactron.profiler import ProfileData


__all__ = [
    "MetricLocation",
    "GenerationInfo",
    "generate_verilog",
]


@dataclass_json
@dataclass
class MetricLocation:
    """Information about the location of a metric in the generated Verilog code.

    Attributes
    ----------
    regs : dict[str, list[str]]
        The location of each register of that metric. The location is a list of
        Verilog identifiers that denote a path consiting of modules names
        (and the signal name at the end) leading to the register wire.
    """

    regs: dict[str, list[str]] = field(default_factory=dict)


@dataclass_json
@dataclass
class TransactionSignalsLocation:
    request: list[str]
    runnable: list[str]
    grant: list[str]


@dataclass_json
@dataclass
class MethodSignalsLocation:
    run: list[str]


@dataclass_json
@dataclass
class GenerationInfo:
    """Various information about the generated circuit.

    Attributes
    ----------
    metrics_location : dict[str, MetricInfo]
        Mapping from a metric name to an object storing Verilog locations
        of its registers.
    """

    metrics_location: dict[str, MetricLocation]
    transaction_signals_location: dict[int, TransactionSignalsLocation]
    method_signals_location: dict[int, MethodSignalsLocation]
    profile_data: ProfileData

    def encode(self, file_name: str):
        """
        Encodes the generation information as JSON and saves it to a file.
        """
        with open(file_name, "w") as fp:
            fp.write(self.to_json())  # type: ignore

    @staticmethod
    def decode(file_name: str) -> "GenerationInfo":
        """
        Loads the generation information from a JSON file.
        """
        with open(file_name, "r") as fp:
            return GenerationInfo.from_json(fp.read())  # type: ignore


def escape_verilog_identifier(identifier: str) -> str:
    """
    Escapes a Verilog identifier according to the language standard.

    From IEEE Std 1364-2001 (IEEE Standard Verilog® Hardware Description Language)

    "2.7.1 Escaped identifiers

    Escaped identifiers shall start with the backslash character and end with white
    space (space, tab, newline). They provide a means of including any of the printable ASCII
    characters in an identifier (the decimal values 33 through 126, or 21 through 7E in hexadecimal)."
    """

    # The standard says how to escape a identifier, but not when. So this is
    # a non-exhaustive list of characters that Yosys escapes (it is used
    # by Amaranth when generating Verilog code).
    characters_to_escape = [".", "$"]

    for char in characters_to_escape:
        if char in identifier:
            # Note the intentional space at the end.
            return f"\\{identifier} "

    return identifier


def get_signal_location(signal: Signal, name_map: SignalDict) -> list[str]:
    raw_location = name_map[signal]

    # Amaranth escapes identifiers when generating Verilog code, but returns non-escaped identifiers
    # in the name map, so we need to escape it manually.
    return [escape_verilog_identifier(component) for component in raw_location]


def collect_metric_locations(name_map: SignalDict) -> dict[str, MetricLocation]:
    metrics_location: dict[str, MetricLocation] = {}

    # Collect information about the location of metric registers in the generated code.
    metrics_manager = HardwareMetricsManager()
    for metric_name, metric in metrics_manager.get_metrics().items():
        metric_loc = MetricLocation()
        for reg_name in metric.regs:
            metric_loc.regs[reg_name] = get_signal_location(
                metrics_manager.get_register_value(metric_name, reg_name), name_map
            )

        metrics_location[metric_name] = metric_loc

    return metrics_location


def collect_transaction_method_signals(
    transaction_manager: TransactionManager, name_map: SignalDict
) -> tuple[dict[int, TransactionSignalsLocation], dict[int, MethodSignalsLocation]]:
    transaction_signals_location: dict[int, TransactionSignalsLocation] = {}
    method_signals_location: dict[int, MethodSignalsLocation] = {}

    method_map = MethodMap(transaction_manager.transactions)
    get_id = IdGenerator()

    for transaction in method_map.transactions:
        request_loc = get_signal_location(transaction.request, name_map)
        runnable_loc = get_signal_location(transaction.runnable, name_map)
        grant_loc = get_signal_location(transaction.grant, name_map)
        transaction_signals_location[get_id(transaction)] = TransactionSignalsLocation(
            request_loc, runnable_loc, grant_loc
        )

    for method in method_map.methods:
        run_loc = get_signal_location(method.run, name_map)
        method_signals_location[get_id(method)] = MethodSignalsLocation(run_loc)

    return (transaction_signals_location, method_signals_location)


def generate_verilog(
    top_module: Elaboratable, ports: list[Signal], top_name: str = "top"
) -> tuple[str, GenerationInfo]:
    fragment = ir.Fragment.get(top_module, platform=None).prepare(ports=ports)
    verilog_text, name_map = verilog.convert_fragment(fragment, name=top_name, emit_src=True, strip_internal_attrs=True)

    transaction_manager = DependencyContext.get().get_dependency(TransactionManagerKey())
    transaction_signals, method_signals = collect_transaction_method_signals(
        transaction_manager, name_map  # type: ignore
    )
    profile_data, _ = ProfileData.make(transaction_manager)
    gen_info = GenerationInfo(
        metrics_location=collect_metric_locations(name_map),  # type: ignore
        transaction_signals_location=transaction_signals,
        method_signals_location=method_signals,
        profile_data=profile_data,
    )

    return verilog_text, gen_info
