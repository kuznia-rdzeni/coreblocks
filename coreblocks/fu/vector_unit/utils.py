from enum import IntEnum, auto

__all__ = ["EEW", "eew_to_bits", "bits_to_eew"]


class EEW(IntEnum):
    w8 = auto()
    w16 = auto()
    w32 = auto()
    w64 = auto()


def eew_to_bits(eew: EEW) -> int:
    if eew == EEW.w8:
        return 8
    elif eew == EEW.w16:
        return 16
    elif eew == EEW.w32:
        return 32
    elif eew == EEW.w64:
        return 64
    else:
        raise ValueError(f"Not known EEW: {eew}")


def bits_to_eew(bits: int) -> EEW:
    if bits == 8:
        return EEW.w8
    elif bits == 16:
        return EEW.w16
    elif bits == 32:
        return EEW.w32
    elif bits == 64:
        return EEW.w64
    else:
        raise ValueError(f"Not known EEW: {bits}")
