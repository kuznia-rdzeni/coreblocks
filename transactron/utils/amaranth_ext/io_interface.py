from typing import Optional
from copy import copy
from amaranth import Shape, ShapeLike, Value, ValueLike, unsigned
from amaranth.lib.wiring import Signature, Flow, Member
from amaranth_types import AbstractInterface, AbstractSignature

__all__ = [
    "IOSignal",
    "SignalIn",
    "SignalOut",
    "IOInterface",
]


class IOSignal(Value):
    _io_flow: Flow
    _io_shape: ShapeLike

    def __init__(self, flow: Flow, shape: Optional[ShapeLike] = None):
        self._io_shape = unsigned(1) if shape is None else shape
        self._io_flow = flow

    # Value abstract methods
    def shape(self):
        return Shape.cast(self._io_shape)

    def _rhs_signals(self):
        # This method should never be called
        # IOSignal is going to be substituted by a Component constructor or be used only as a type
        raise NotImplementedError

    # Signal API compatiblity - Signal cannot be subclassed
    @staticmethod
    def like(
        other: ValueLike, *, name: Optional[str] = None, name_suffix: Optional[str] = None, src_loc_at=None, **kwargs
    ):
        raise NotImplementedError


class SignalIn(IOSignal):
    def __init__(self, shape: Optional[ShapeLike] = 0):
        super().__init__(Flow.In, shape)


class SignalOut(IOSignal):
    def __init__(self, shape: Optional[ShapeLike] = 0):
        super().__init__(Flow.Out, shape)


class IOInterface(AbstractInterface[AbstractSignature]):
    _is_flipped: bool

    def _get_flipped(self) -> bool:
        try:
            return self._is_flipped
        except AttributeError:
            return False

    def _to_members_list(self, *, _name_prefix: str = "") -> dict[str, Member]:
        ret = {}
        for m_name in dir(self):
            if m_name == "signature" or m_name == "flipped" or m_name.startswith("_"):
                continue

            m_val = getattr(self, m_name)
            if isinstance(m_val, IOSignal):
                if m_val._io_flow is Flow.In:
                    ret[m_name] = Flow.In(m_val._io_shape)
                if m_val._io_flow is Flow.Out:
                    ret[m_name] = Flow.Out(m_val._io_shape)

            elif isinstance(m_val, IOInterface):
                flow_direction = Flow.In if m_val._get_flipped() else Flow.Out
                ret[m_name] = flow_direction(
                    Signature(m_val._to_members_list(_name_prefix=_name_prefix + m_name + "."))
                )

            else:
                raise AttributeError(
                    f"Illegal attribute `{_name_prefix + m_name}`. "
                    "Expected IOSignal, SignalIn, SignalOut or IOInterface"
                )

        return ret

    @property
    def signature(self) -> Signature:
        if self._get_flipped():
            return Signature(Signature(self._to_members_list()).flip().members)
        else:
            return Signature(self._to_members_list())

    def flipped(self) -> "IOInterface":
        x = copy(self)
        x._is_flipped = not self._get_flipped()
        return x


# class SubInterface(IOInterface):
#    def __init__(self):
#        self.i = SignalIn(1)
#
# class WishboneInterface(IOInterface):
#    def __init__(self):
#        self.i = SignalIn(2)
#        self.o = SignalOut(2)
#        self.s = SubInterface()
#       self.f = SubInterface().flipped()
#        self.z = 1


# print(WishboneInterface().signature)
