"""
This type stub file was generated by pyright.
"""

__all__ = ["ClockDomain", "DomainError"]

class DomainError(Exception): ...

class ClockDomain:
    """Synchronous domain.

    Paramet"""

    def __init__(self, name=..., *, clk_edge=..., reset_less=..., async_reset=..., local=...) -> None: ...
    def rename(self, new_name): ...
