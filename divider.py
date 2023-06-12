
def stage4(a:int, b:int) -> tuple[int, int]:
    def stage(a:int, b:int) -> tuple[int, int]:
        if a >= b:
            return (a - b), 1
        else:
            return a, 0
    
    r3, q3 = stage(            ((a & 0b1000) >> 3), b)
    r2, q2 = stage((r3 << 1) | ((a & 0b0100) >> 2), b)
    r1, q1 = stage((r2 << 1) | ((a & 0b0010) >> 1), b)
    r0, q0 = stage((r1 << 1) | ((a & 0b0001) >> 0), b)
    
    q = (q3 << 3) | (q2 << 2) | (q1 << 1) | q0

    return q, r0


print(stage4(1, -1))