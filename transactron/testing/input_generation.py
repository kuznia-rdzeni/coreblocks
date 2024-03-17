import random
from typing import Optional
from transactron.utils import SimpleLayout


def generate_based_on_layout(layout: SimpleLayout, *, max_bits: Optional[int] = None):
    d = {}
    for elem in layout:
        if isinstance(elem[1], int):
            if max_bits is None:
                max_val = 2 ** elem[1]
            else:
                max_val = 2 ** min(max_bits, elem[1])
            d[elem[0]] = random.randrange(max_val)
        else:
            d[elem[0]] = generate_based_on_layout(elem[1])
    return d
