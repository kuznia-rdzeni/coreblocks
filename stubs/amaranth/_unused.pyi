__all__ = ["UnusedMustUse", "MustUse"]


class UnusedMustUse(Warning):
    pass


class MustUse:
    _MustUse__silence: bool
    _MustUse__warning: type[UnusedMustUse]

