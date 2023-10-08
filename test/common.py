import unittest
import os
import functools
import random
from contextlib import contextmanager, nullcontext
from typing import Callable, Generic, Mapping, Union, Generator, TypeVar, Optional, Any, cast, Type, TypeGuard

from amaranth import *
from amaranth.hdl.ast import Statement
from amaranth.sim import *
from amaranth.sim.core import Command

from transactron.core import SignalBundle, Method, TransactionModule
from transactron.lib import AdapterBase, AdapterTrans
from transactron._utils import method_def_helper
from coreblocks.utils import ValueLike, HasElaborate, HasDebugSignals, auto_debug_signals, LayoutLike, ModuleConnector
from .gtkw_extension import write_vcd_ext










