from dataclasses import dataclass, field
from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class CoreMetricLocation:
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
class CoreGenInfo:
    """Various information about the generated core.

    Attributes
    ----------
    core_metrics_location : dict[str, CoreMetricInfo]
        Mapping from a metric name to an object storing Verilog locations
        of its registers.
    """

    core_metrics_location: dict[str, CoreMetricLocation] = field(default_factory=dict)

    def encode(self, file_name: str):
        """
        Encodes the generation information as JSON and saves it to a file.
        """
        with open(file_name, "w") as fp:
            fp.write(self.to_json())  # type: ignore

    @staticmethod
    def decode(file_name: str) -> "CoreGenInfo":
        """
        Loads the generation information from a JSON file.
        """
        with open(file_name, "r") as fp:
            return CoreGenInfo.from_json(fp.read())  # type: ignore
