from dataclasses import dataclass


@dataclass(frozen=True)
class QSFTable:
    intervals: list[int]
    bounds: list[list[int]]
    digits: list[tuple[int, int]]


"""
Table for radix 4 with parameter a = 2.
Table taken from "Digital Arithmetic" Chapter 8
"""
R4A2RED = QSFTable(
    [8, 9, 10, 11, 12, 13, 14, 15],
    [
        [-13, -4, 4, 12],
        [-15, -6, 4, 14],
        [-16, -6, 4, 15],
        [-18, -6, 4, 16],
        [-20, -8, 6, 20],
        [-20, -8, 6, 20],
        [-22, -8, 8, 20],
        [-24, -8, 8, 24],
    ],
    [(1, 2), (1, 1), (0, 0), (0, 1), (0, 2)],
)
