import os
import re
import operator
import logging
from functools import reduce
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from typing import TypeAlias

from amaranth import *
from amaranth.tracer import get_src_loc

from transactron.utils import SrcLoc
from transactron.utils._typing import ModuleLike, ValueLike
from transactron.utils.dependencies import DependencyContext, ListKey

LogLevel: TypeAlias = int


@dataclass_json
@dataclass
class LogRecordInfo:
    """Simulator-backend-agnostic information about a log record that can
    be serialized and used outside the Amaranth context.

    Attributes
    ----------
    logger_name: str

    level: LogLevel
        The severity level of the log.
    format_str: str
        The template of the message. Should follow PEP 3101 standard.
    location: SrcLoc
        Source location of the log.
    """

    logger_name: str
    level: LogLevel
    format_str: str
    location: SrcLoc

    def format(self, *args) -> str:
        """Format the log message with a set of concrete arguments."""

        return self.format_str.format(*args)


@dataclass
class LogRecord(LogRecordInfo):
    """A LogRecord instance represents an event being logged.

    Attributes
    ----------
    trigger: Signal
        Amaranth signal triggering the log.
    fields: Signal
        Amaranth signals that will be used to format the message.
    """

    trigger: Signal
    fields: list[Signal] = field(default_factory=list)


@dataclass(frozen=True)
class LogKey(ListKey[LogRecord]):
    pass


class HardwareLogger:
    """A class for creating log messages in the hardware.

    Intuitively, the hardware logger works similarly to a normal software
    logger. You can log a message anywhere in the circuit, but due to the
    parallel nature of the hardware you must specify a special trigger signal
    which will indicate if a message shall be reported in that cycle.

    Hardware logs are evaluated and printed during simulation, so both
    the trigger and the format fields are Amaranth values, i.e.
    signals or arbitrary Amaranth expressions.

    Instances of the HardwareLogger class represent a logger for a single
    submodule of the circuit. Exactly how a "submodule" is defined is up
    to the developer. Submodule are identified by a unique string and
    the names can be nested. Names are organized into a namespace hierarchy
    where levels are separated by periods, much like the Python package
    namespace. So in the instance, submodules names might be "frontend"
    for the upper level, and "frontend.icache" and "frontend.bpu" for
    the sub-levels. There is no arbitrary limit to the depth of nesting.

    Attributes
    ----------
    name: str
        Name of this logger.
    """

    def __init__(self, name: str):
        """
        Parameters
        ----------
        name: str
            Name of this logger. Hierarchy levels are separated by periods,
            e.g. "backend.fu.jumpbranch".
        """
        self.name = name

    def log(self, m: ModuleLike, level: LogLevel, trigger: ValueLike, format: str, *args, src_loc_at: int = 0):
        """Registers a hardware log record with the given severity.

        Parameters
        ----------
        m: ModuleLike
            The module for which the log record is added.
        trigger: ValueLike
            If the value of this Amaranth expression is true, the log will reported.
        format: str
            The format of the message as defined in PEP 3101.
        *args
            Amaranth values that will be read during simulation and used to format
            the message.
        src_loc_at: int, optional
            How many stack frames below to look for the source location, used to
            identify the failing assertion.
        """

        def local_src_loc(src_loc: SrcLoc):
            return (os.path.relpath(src_loc[0]), src_loc[1])

        src_loc = local_src_loc(get_src_loc(src_loc_at + 1))

        trigger_signal = Signal()
        m.d.comb += trigger_signal.eq(trigger)

        record = LogRecord(
            logger_name=self.name, level=level, format_str=format, location=src_loc, trigger=trigger_signal
        )

        for arg in args:
            sig = Signal.like(arg)
            m.d.top_comb += sig.eq(arg)
            record.fields.append(sig)

        dependencies = DependencyContext.get()
        dependencies.add_dependency(LogKey(), record)

    def debug(self, m: ModuleLike, trigger: ValueLike, format: str, *args, **kwargs):
        """Log a message with severity 'DEBUG'.

        See `HardwareLogger.log` function for more details.
        """
        self.log(m, logging.DEBUG, trigger, format, *args, **kwargs)

    def info(self, m: ModuleLike, trigger: ValueLike, format: str, *args, **kwargs):
        """Log a message with severity 'INFO'.

        See `HardwareLogger.log` function for more details.
        """
        self.log(m, logging.INFO, trigger, format, *args, **kwargs)

    def warning(self, m: ModuleLike, trigger: ValueLike, format: str, *args, **kwargs):
        """Log a message with severity 'WARNING'.

        See `HardwareLogger.log` function for more details.
        """
        self.log(m, logging.WARNING, trigger, format, *args, **kwargs)

    def error(self, m: ModuleLike, trigger: ValueLike, format: str, *args, **kwargs):
        """Log a message with severity 'ERROR'.

        This severity level has special semantics. If a log with this serverity
        level is triggered, the simulation will be terminated.

        See `HardwareLogger.log` function for more details.
        """
        self.log(m, logging.ERROR, trigger, format, *args, **kwargs)

    def assertion(
        self, m: ModuleLike, value: Value, format: str = "Assertion failed", *args, src_loc_at: int = 0, **kwargs
    ):
        """Define an assertion.

        This function might help find some hardware bugs which might otherwise be
        hard to detect. If `value` is false, it will terminate the simulation or
        it can also be used to turn on a warning LED on a board.

        Internally, this is a convenience wrapper over log.error.

        See `HardwareLogger.log` function for more details.
        """
        self.error(m, ~value, format, *args, **kwargs, src_loc_at=src_loc_at + 1)


def get_log_records(level: LogLevel, namespace_regexp: str = ".*") -> list[LogRecord]:
    """Get log records in for the given severity level and in the
    specified namespace.

    This function returns all log records with the severity bigger or equal
    to the specified level and belonging to the specified namespace.

    Parameters
    ----------
    level: LogLevel
        The minimum severity level.
    namespace: str, optional
        The regexp of the namespace. If not specified, logs from all namespaces
        will be processed.
    """

    dependencies = DependencyContext.get()
    all_logs = dependencies.get_dependency(LogKey())
    return [rec for rec in all_logs if rec.level >= level and re.search(namespace_regexp, rec.logger_name)]


def get_trigger_bit(level: LogLevel, namespace_regexp: str = ".*") -> Value:
    """Get a trigger bit for logs of the given severity level and
    in the specified namespace.

    The signal returned by this function is high whenever the trigger signal
    of any of the records with the severity bigger or equal to the specified
    level is high.

    Parameters
    ----------
    level: LogLevel
        The minimum severity level.
    namespace: str, optional
        The regexp of the namespace. If not specified, logs from all namespaces
        will be processed.
    """

    return reduce(operator.or_, [rec.trigger for rec in get_log_records(level, namespace_regexp)], C(0))
