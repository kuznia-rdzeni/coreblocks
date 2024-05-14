from collections.abc import Sequence
from transactron.utils import *
from amaranth import *
from amaranth import tracer
from typing import Optional, Callable, Iterator, TYPE_CHECKING
from .transaction_base import *
from .sugar import def_method
from contextlib import contextmanager
from transactron.utils.assign import AssignArg

if TYPE_CHECKING:
    from .tmodule import TModule

__all__ = ["Method"]


class Method(TransactionBase):
    """Transactional method.

    A `Method` serves to interface a module with external `Transaction`\\s
    or `Method`\\s. It can be called by at most once in a given clock cycle.
    When a given `Method` is required by multiple `Transaction`\\s
    (either directly, or indirectly via another `Method`) simultenaously,
    at most one of them is granted by the `TransactionManager`, and the rest
    of them must wait. (Non-exclusive methods are an exception to this
    behavior.) Calling a `Method` always takes a single clock cycle.

    Data is combinationally transferred between to and from `Method`\\s
    using Amaranth structures (`View` with a `StructLayout`). The transfer
    can take place in both directions at the same time: from the called
    `Method` to the caller (`data_out`) and from the caller to the called
    `Method` (`data_in`).

    A module which defines a `Method` should use `body` or `def_method`
    to describe the method's effect on the module state.

    Attributes
    ----------
    name: str
        Name of this `Method`.
    ready: Signal, in
        Signals that the method is ready to run in the current cycle.
        Typically defined by calling `body`.
    run: Signal, out
        Signals that the method is called in the current cycle by some
        `Transaction`. Defined by the `TransactionManager`.
    data_in: MethodStruct, out
        Contains the data passed to the `Method` by the caller
        (a `Transaction` or another `Method`).
    data_out: MethodStruct, in
        Contains the data passed from the `Method` to the caller
        (a `Transaction` or another `Method`). Typically defined by
        calling `body`.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        i: MethodLayout = (),
        o: MethodLayout = (),
        nonexclusive: bool = False,
        combiner: Optional[Callable[[Module, Sequence[MethodStruct], Value], AssignArg]] = None,
        single_caller: bool = False,
        src_loc: int | SrcLoc = 0,
    ):
        """
        Parameters
        ----------
        name: str or None
            Name hint for this `Method`. If `None` (default) the name is
            inferred from the variable name this `Method` is assigned to.
        i: method layout
            The format of `data_in`.
        o: method layout
            The format of `data_out`.
        nonexclusive: bool
            If true, the method is non-exclusive: it can be called by multiple
            transactions in the same clock cycle. If such a situation happens,
            the method still is executed only once, and each of the callers
            receive its output. Nonexclusive methods cannot have inputs.
        combiner: (Module, Sequence[MethodStruct], Value) -> AssignArg
            If `nonexclusive` is true, the combiner function combines the
            arguments from multiple calls to this method into a single
            argument, which is passed to the method body. The third argument
            is a bit vector, whose n-th bit is 1 if the n-th call is active
            in a given cycle.
        single_caller: bool
            If true, this method is intended to be called from a single
            transaction. An error will be thrown if called from multiple
            transactions.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.
        """
        super().__init__(src_loc=get_src_loc(src_loc))

        def default_combiner(m: Module, args: Sequence[MethodStruct], runs: Value) -> AssignArg:
            ret = Signal(from_method_layout(i))
            for k in OneHotSwitchDynamic(m, runs):
                m.d.comb += ret.eq(args[k])
            return ret

        self.owner, owner_name = get_caller_class_name(default="$method")
        self.name = name or tracer.get_var_name(depth=2, default=owner_name)
        self.ready = Signal(name=self.owned_name + "_ready")
        self.run = Signal(name=self.owned_name + "_run")
        self.data_in: MethodStruct = Signal(from_method_layout(i))
        self.data_out: MethodStruct = Signal(from_method_layout(o))
        self.nonexclusive = nonexclusive
        self.combiner: Callable[[Module, Sequence[MethodStruct], Value], AssignArg] = combiner or default_combiner
        self.single_caller = single_caller
        self.validate_arguments: Optional[Callable[..., ValueLike]] = None
        if nonexclusive:
            assert len(self.data_in.as_value()) == 0 or combiner is not None

    @property
    def layout_in(self):
        return self.data_in.shape()

    @property
    def layout_out(self):
        return self.data_out.shape()

    @staticmethod
    def like(other: "Method", *, name: Optional[str] = None, src_loc: int | SrcLoc = 0) -> "Method":
        """Constructs a new `Method` based on another.

        The returned `Method` has the same input/output data layouts as the
        `other` `Method`.

        Parameters
        ----------
        other : Method
            The `Method` which serves as a blueprint for the new `Method`.
        name : str, optional
            Name of the new `Method`.
        src_loc: int | SrcLoc
            How many stack frames deep the source location is taken from.
            Alternatively, the source location to use instead of the default.

        Returns
        -------
        Method
            The freshly constructed `Method`.
        """
        return Method(name=name, i=other.layout_in, o=other.layout_out, src_loc=get_src_loc(src_loc))

    def proxy(self, m: "TModule", method: "Method"):
        """Define as a proxy for another method.

        The calls to this method will be forwarded to `method`.

        Parameters
        ----------
        m : TModule
            Module in which operations on signals should be executed,
            `proxy` uses the combinational domain only.
        method : Method
            Method for which this method is a proxy for.
        """

        @def_method(m, self, ready=method.ready)
        def _(arg):
            return method(m, arg)

    @contextmanager
    def body(
        self,
        m: "TModule",
        *,
        ready: ValueLike = C(1),
        out: ValueLike = C(0, 0),
        validate_arguments: Optional[Callable[..., ValueLike]] = None,
    ) -> Iterator[MethodStruct]:
        """Define method body

        The `body` context manager can be used to define the actions
        performed by a `Method` when it's run. Each assignment added to
        a domain under `body` is guarded by the `run` signal.
        Combinational assignments which do not need to be guarded by `run`
        can be added to `m.d.av_comb` or `m.d.top_comb` instead of `m.d.comb`.
        `Method` calls can be performed under `body`.

        Parameters
        ----------
        m : TModule
            Module in which operations on signals should be executed,
            `body` uses the combinational domain only.
        ready : Signal, in
            Signal to indicate if the method is ready to be run. By
            default it is `Const(1)`, so the method is always ready.
            Assigned combinationially to the `ready` attribute.
        out : Value, in
            Data generated by the `Method`, which will be passed to
            the caller (a `Transaction` or another `Method`). Assigned
            combinationally to the `data_out` attribute.
        validate_arguments: Optional[Callable[..., ValueLike]]
            Function that takes input arguments used to call the method
            and checks whether the method can be called with those arguments.
            It instantiates a combinational circuit for each
            method caller. By default, there is no function, so all arguments
            are accepted.

        Returns
        -------
        data_in : Record, out
            Data passed from the caller (a `Transaction` or another
            `Method`) to this `Method`.

        Examples
        --------
        .. highlight:: python
        .. code-block:: python

            m = Module()
            my_sum_method = Method(i = Layout([("arg1",8),("arg2",8)]))
            sum = Signal(16)
            with my_sum_method.body(m, out = sum) as data_in:
                m.d.comb += sum.eq(data_in.arg1 + data_in.arg2)
        """
        if self.defined:
            raise RuntimeError(f"Method '{self.name}' already defined")
        self.def_order = next(TransactionBase.def_counter)
        self.validate_arguments = validate_arguments

        m.d.av_comb += self.ready.eq(ready)
        m.d.top_comb += self.data_out.eq(out)
        with self.context(m):
            with m.AvoidedIf(self.run):
                yield self.data_in

    def _validate_arguments(self, arg_rec: MethodStruct) -> ValueLike:
        if self.validate_arguments is not None:
            return self.ready & method_def_helper(self, self.validate_arguments, arg_rec)
        return self.ready

    def __call__(
        self, m: "TModule", arg: Optional[AssignArg] = None, enable: ValueLike = C(1), /, **kwargs: AssignArg
    ) -> MethodStruct:
        """Call a method.

        Methods can only be called from transaction and method bodies.
        Calling a `Method` marks, for the purpose of transaction scheduling,
        the dependency between the calling context and the called `Method`.
        It also connects the method's inputs to the parameters and the
        method's outputs to the return value.

        Parameters
        ----------
        m : TModule
            Module in which operations on signals should be executed,
        arg : Value or dict of Values
            Call argument. Can be passed as a `View` of the method's
            input layout or as a dictionary. Alternative syntax uses
            keyword arguments.
        enable : Value
            Configures the call as enabled in the current clock cycle.
            Disabled calls still lock the called method in transaction
            scheduling. Calls are by default enabled.
        **kwargs : Value or dict of Values
            Allows to pass method arguments using keyword argument
            syntax. Equivalent to passing a dict as the argument.

        Returns
        -------
        data_out : MethodStruct
            The result of the method call.

        Examples
        --------
        .. highlight:: python
        .. code-block:: python

            m = Module()
            with Transaction().body(m):
                ret = my_sum_method(m, arg1=2, arg2=3)

        Alternative syntax:

        .. highlight:: python
        .. code-block:: python

            with Transaction().body(m):
                ret = my_sum_method(m, {"arg1": 2, "arg2": 3})
        """
        arg_rec = Signal.like(self.data_in)

        if arg is not None and kwargs:
            raise ValueError(f"Method '{self.name}' call with both keyword arguments and legacy record argument")

        if arg is None:
            arg = kwargs

        enable_sig = Signal(name=self.owned_name + "_enable")
        m.d.av_comb += enable_sig.eq(enable)
        m.d.top_comb += assign(arg_rec, arg, fields=AssignType.ALL)

        caller = TransactionBase.get()
        if not all(ctrl_path.exclusive_with(m.ctrl_path) for ctrl_path, _, _ in caller.method_calls[self]):
            raise RuntimeError(f"Method '{self.name}' can't be called twice from the same caller '{caller.name}'")
        caller.method_calls[self].append((m.ctrl_path, arg_rec, enable_sig))

        if self not in caller.method_uses:
            arg_rec_use = Signal(self.layout_in)
            arg_rec_enable_sig = Signal()
            caller.method_uses[self] = (arg_rec_use, arg_rec_enable_sig)

        return self.data_out

    def __repr__(self) -> str:
        return "(method {})".format(self.name)

    def debug_signals(self) -> SignalBundle:
        return [self.ready, self.run, self.data_in, self.data_out]
