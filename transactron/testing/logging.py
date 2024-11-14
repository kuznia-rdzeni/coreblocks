from collections.abc import Callable, Iterable
from typing import Any
import logging
import itertools

from amaranth.sim._async import ProcessContext
from transactron.lib import logging as tlog
from transactron.utils.dependencies import DependencyContext
from .tick_count import TicksKey


__all__ = ["make_logging_process", "parse_logging_level"]


def parse_logging_level(str: str) -> tlog.LogLevel:
    """Parse the log level from a string.

    The level can be either a non-negative integer or a string representation
    of one of the predefined levels.

    Raises an exception if the level cannot be parsed.
    """
    str = str.upper()
    names_mapping = logging.getLevelNamesMapping()
    if str in names_mapping:
        return names_mapping[str]

    # try convert to int
    try:
        return int(str)
    except ValueError:
        pass

    raise ValueError("Log level must be either {error, warn, info, debug} or a non-negative integer.")


_sim_cycle: int = 0


class _LogFormatter(logging.Formatter):
    """
    Log formatter to provide colors and to inject simulator times into
    the log messages. Adapted from https://stackoverflow.com/a/56944256/3638629
    """

    magenta = "\033[0;35m"
    grey = "\033[0;34m"
    blue = "\033[0;34m"
    yellow = "\033[0;33m"
    red = "\033[0;31m"
    reset = "\033[0m"

    loglevel2colour = {
        logging.DEBUG: grey + "{}" + reset,
        logging.INFO: magenta + "{}" + reset,
        logging.WARNING: yellow + "{}" + reset,
        logging.ERROR: red + "{}" + reset,
    }

    def format(self, record: logging.LogRecord):
        level_name = self.loglevel2colour[record.levelno].format(record.levelname)
        return f"{_sim_cycle} {level_name} {record.name} {record.getMessage()}"


def make_logging_process(level: tlog.LogLevel, namespace_regexp: str, on_error: Callable[[], Any]):
    combined_trigger = tlog.get_trigger_bit(level, namespace_regexp)
    records = tlog.get_log_records(level, namespace_regexp)

    root_logger = logging.getLogger()

    def handle_logs(record_vals: Iterable[int]) -> None:
        it = iter(record_vals)

        for record in records:
            trigger = next(it)
            values = [next(it) for _ in record.fields]

            if not trigger:
                continue

            formatted_msg = record.format(*values)

            logger = root_logger.getChild(record.logger_name)
            logger.log(
                record.level,
                "[%s:%d] %s",
                record.location[0],
                record.location[1],
                formatted_msg,
            )

            if record.level >= logging.ERROR:
                on_error()

    async def log_process(sim: ProcessContext) -> None:
        global _sim_cycle
        ticks = DependencyContext.get().get_dependency(TicksKey())

        async for _, _, ticks_val, combined_trigger_val, *record_vals in (
            sim.tick()
            .sample(ticks, combined_trigger)
            .sample(*itertools.chain(*([record.trigger] + record.fields for record in records)))
        ):
            if not combined_trigger_val:
                continue
            _sim_cycle = ticks_val
            handle_logs(record_vals)

    return log_process
