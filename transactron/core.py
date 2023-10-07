from collections import defaultdict, deque
from collections.abc import Sequence, Iterable, Callable, Mapping, Iterator
from contextlib import contextmanager
from typing import ClassVar, NoReturn, TypeAlias, TypedDict, Union, Optional, Tuple
from typing_extensions import Self
from amaranth import tracer
from itertools import count, chain, filterfalse, product
from amaranth.hdl.dsl import FSM, _ModuleBuilderDomain

from coreblocks.utils import AssignType, assign, ModuleConnector
from coreblocks.utils.utils import OneHotSwitchDynamic
from ._utils import *
from coreblocks.utils._typing import ValueLike, SignalBundle, HasElaborate, SwitchKey, ModuleLike

__all__ = [
    "MethodLayout",
    "Priority",
    "TModule",
    "TransactionManager",
    "TransactionContext",
    "TransactionModule",
    "Transaction",
    "Method",
    "def_method",
]


