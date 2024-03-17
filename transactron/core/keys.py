from transactron.utils import *
from typing import TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .manager import TransactionManager  # noqa: F401 because of https://github.com/PyCQA/pyflakes/issues/571

__all__ = ["TransactionManagerKey"]


@dataclass(frozen=True)
class TransactionManagerKey(SimpleKey["TransactionManager"]):
    pass
