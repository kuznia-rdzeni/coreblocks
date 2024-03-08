from dataclasses import dataclass, field
from dataclasses_json import dataclass_json

from amaranth import *
from amaranth.back import verilog
from amaranth.hdl import Fragment

from transactron.lib.metrics import HardwareMetricsManager
from transactron.utils._typing import SrcLoc
from transactron.utils.assertion import assert_bits

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amaranth.hdl._ast import SignalDict


__all__ = [
    "MetricLocation",
    "AssertLocation",
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
class AssertLocation:
    """Information about an assert signal in the generated Verilog code.

    Attributes
    ----------
    location : list[str]
        The location of the assert signal. The location is a list of Verilog
        identifiers that denote a path consisting of module names (and the
        signal name at the end) leading to the signal wire.
    src_loc : SrcLoc
        Source location of the assertion.
    """

    location: list[str]
    src_loc: SrcLoc


@dataclass_json
@dataclass
class GenerationInfo:
    """Various information about the generated circuit.

    Attributes
    ----------
    metrics_location : dict[str, MetricInfo]
        Mapping from a metric name to an object storing Verilog locations
        of its registers.
    asserts : list[AssertLocation]
        Locations and metadata for assertion signals.
    """

    metrics_location: dict[str, MetricLocation] = field(default_factory=dict)
    asserts: list[AssertLocation] = field(default_factory=list)

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


def get_signal_location(signal: Signal, name_map: "SignalDict") -> list[str]:
    raw_location = name_map[signal]

    # Amaranth escapes identifiers when generating Verilog code, but returns non-escaped identifiers
    # in the name map, so we need to escape it manually.
    return [escape_verilog_identifier(component) for component in raw_location]


def collect_metric_locations(name_map: "SignalDict") -> dict[str, MetricLocation]:
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


def collect_asserts(name_map: "SignalDict") -> list[AssertLocation]:
    asserts: list[AssertLocation] = []

    for v, src_loc in assert_bits():
        asserts.append(AssertLocation(get_signal_location(v, name_map), src_loc))

    return asserts


def generate_verilog(
    top_module: Elaboratable, ports: list[Signal], top_name: str = "top"
) -> tuple[str, GenerationInfo]:
    fragment = Fragment.get(top_module, platform=None).prepare(ports=ports)
    verilog_text, name_map = verilog.convert_fragment(fragment, name=top_name, emit_src=True, strip_internal_attrs=True)

    gen_info = GenerationInfo(metrics_location=collect_metric_locations(name_map), asserts=collect_asserts(name_map))

    return verilog_text, gen_info