from typing import TypeVar, Type, Any

from transactron.utils import make_hashable

__all__ = ["DependentCache"]

T = TypeVar("T")


class DependentCache:
    """
    Cache for classes, that depend on the `DependentCache` class itself.

    Cached classes may accept one positional argument in the constructor, where this `DependentCache` class will
    be passed. Classes may define any number keyword arguments in the constructor and separate cache entry will
    be created for each set of the arguments.

    Methods
    -------
    get: T, **kwargs -> T
        Gets class `cls` from cache. Caches `cls` reference if this is the first call for it.
        Optionally accepts `kwargs` for additional arguments in `cls` constructor.

    """

    def __init__(self):
        self._depcache: dict[tuple[Type, Any], Type] = {}

    def get(self, cls: Type[T], **kwargs) -> T:
        cache_key = make_hashable(kwargs)
        v = self._depcache.get((cls, cache_key), None)
        if v is None:
            positional_count = cls.__init__.__code__.co_argcount

            # first positional arg is `self` field, second may be `DependentCache`
            if positional_count > 2:
                raise KeyError(f"Too many positional arguments in {cls!r} constructor")

            if positional_count > 1:
                v = cls(self, **kwargs)
            else:
                v = cls(**kwargs)
            self._depcache[(cls, cache_key)] = v
        return v
