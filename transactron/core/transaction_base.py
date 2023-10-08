from typing import Union, Tuple, ClassVar, Iterator, Optional, TYPE_CHECKING, TypedDict
from typing_extensions import Self
from itertools import count
from contextlib import contextmanager
from .typing import ValueLike
from .modules import Priority
from ..graph import Owned

if TYPE_CHECKING:
    from .method import Method
    from .transaction import Transaction
    from .modules import TModule

class RelationBase(TypedDict):
    end: "TransactionBase"
    priority: Priority
    conflict: bool


class Relation(RelationBase):
    start: "TransactionBase"


class TransactionBase(Owned):
    stack: ClassVar[list["TransactionBase"]] = []
    def_counter: ClassVar[count] = count()
    def_order: int
    defined: bool = False
    name: str

    def __init__(self):
        self.method_uses: dict["Method", Tuple[ValueLike, ValueLike]] = dict()
        self.relations: list[RelationBase] = []
        self.simultaneous_list: list["TransactionBase"] = []
        self.independent_list: list["TransactionBase"] = []

    def add_conflict(self, end: "TransactionBase", priority: Priority = Priority.UNDEFINED) -> None:
        """Registers a conflict.

        Record that that the given `Transaction` or `Method` cannot execute
        simultaneously with this `Method` or `Transaction`. Typical reason
        is using a common resource (register write or memory port).

        Parameters
        ----------
        end: Transaction or Method
            The conflicting `Transaction` or `Method`
        priority: Priority, optional
            Is one of conflicting `Transaction`\\s or `Method`\\s prioritized?
            Defaults to undefined priority relation.
        """
        self.relations.append(RelationBase(end=end, priority=priority, conflict=True))

    def schedule_before(self, end: "TransactionBase") -> None:
        """Adds a priority relation.

        Record that that the given `Transaction` or `Method` needs to be
        scheduled before this `Method` or `Transaction`, without adding
        a conflict. Typical reason is data forwarding.

        Parameters
        ----------
        end: Transaction or Method
            The other `Transaction` or `Method`
        """
        self.relations.append(RelationBase(end=end, priority=Priority.LEFT, conflict=False))

    def use_method(self, method: "Method", arg: ValueLike, enable: ValueLike):
        if method in self.method_uses:
            raise RuntimeError(f"Method '{method.name}' can't be called twice from the same transaction '{self.name}'")
        self.method_uses[method] = (arg, enable)

    def simultaneous(self, *others: "TransactionBase") -> None:
        """Adds simultaneity relations.

        The given `Transaction`\\s or `Method``\\s will execute simultaneously
        (in the same clock cycle) with this `Transaction` or `Method`.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s to be executed simultaneously.
        """
        self.simultaneous_list += others

    def simultaneous_alternatives(self, *others: "TransactionBase") -> None:
        """Adds exclusive simultaneity relations.

        Each of the given `Transaction`\\s or `Method``\\s will execute
        simultaneously (in the same clock cycle) with this `Transaction` or
        `Method`. However, each of the given `Transaction`\\s or `Method`\\s
        will be separately considered for execution.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s to be executed simultaneously,
            but mutually exclusive, with this `Transaction` or `Method`.
        """
        self.simultaneous(*others)
        others[0]._independent(*others[1:])

    def _independent(self, *others: "TransactionBase") -> None:
        """Adds independence relations.

        This `Transaction` or `Method`, together with all the given
        `Transaction`\\s or `Method`\\s, will never be considered (pairwise)
        for simultaneous execution.

        Warning: this function is an implementation detail, do not use in
        user code.

        Parameters
        ----------
        *others: Transaction or Method
            The `Transaction`\\s or `Method`\\s which, together with this
            `Transaction` or `Method`, need to be independently considered
            for execution.
        """
        self.independent_list += others

    @contextmanager
    def context(self, m: "TModule") -> Iterator[Self]:
        parent = TransactionBase.peek()
        if parent is not None:
            parent.schedule_before(self)

        TransactionBase.stack.append(self)

        try:
            yield self
        finally:
            TransactionBase.stack.pop()

    @classmethod
    def get(cls) -> Self:
        ret = cls.peek()
        if ret is None:
            raise RuntimeError("No current body")
        return ret

    @classmethod
    def peek(cls) -> Optional[Self]:
        if not TransactionBase.stack:
            return None
        if not isinstance(TransactionBase.stack[-1], cls):
            raise RuntimeError(f"Current body not a {cls.__name__}")
        return TransactionBase.stack[-1]

    @property
    def owned_name(self):
        if self.owner is not None and self.owner.__class__.__name__ != self.name:
            return f"{self.owner.__class__.__name__}_{self.name}"
        else:
            return self.name
