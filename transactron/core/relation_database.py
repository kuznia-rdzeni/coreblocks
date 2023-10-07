from enum import Enum, auto
from typing import Iterable, TypedDict, Union, TypeAlias
from itertools import chain
from collections import defaultdict
from .method import Method
from .transaction import Transaction
from .transaction_base import TransactionBase
from .typing import TransactionOrMethod

__all__ = [
        'Priority'
        ]


class Priority(Enum):
    #: Conflicting transactions/methods don't have a priority order.
    UNDEFINED = auto()
    #: Left transaction/method is prioritized over the right one.
    LEFT = auto()
    #: Right transaction/method is prioritized over the left one.
    RIGHT = auto()


class RelationBase(TypedDict):
    end: TransactionOrMethod
    priority: Priority
    conflict: bool


class Relation(RelationBase):
    start: TransactionOrMethod


class MethodMap:
    def __init__(self, transactions: Iterable["Transaction"]):
        self.methods_by_transaction = dict[Transaction, list[Method]]()
        self.transactions_by_method = defaultdict[Method, list[Transaction]](list)

        def rec(transaction: Transaction, source: TransactionBase):
            for method in source.method_uses.keys():
                if not method.defined:
                    raise RuntimeError(f"Trying to use method '{method.name}' which is not defined yet")
                if method in self.methods_by_transaction[transaction]:
                    raise RuntimeError(f"Method '{method.name}' can't be called twice from the same transaction")
                self.methods_by_transaction[transaction].append(method)
                self.transactions_by_method[method].append(transaction)
                rec(transaction, method)

        for transaction in transactions:
            self.methods_by_transaction[transaction] = []
            rec(transaction, transaction)

    def transactions_for(self, elem: TransactionOrMethod) -> Iterable["Transaction"]:
        if isinstance(elem, Transaction):
            return [elem]
        else:
            return self.transactions_by_method[elem]

    @property
    def methods(self) -> Iterable["Method"]:
        return self.transactions_by_method.keys()

    @property
    def transactions(self) -> Iterable["Transaction"]:
        return self.methods_by_transaction.keys()

    @property
    def methods_and_transactions(self) -> Iterable[TransactionOrMethod]:
        return chain(self.methods, self.transactions)
