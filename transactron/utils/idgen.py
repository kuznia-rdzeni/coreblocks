__all__ = ["IdGenerator"]


class IdGenerator:
    def __init__(self):
        self.id_map = dict[int, int]()
        self.id_seq = 0

    def __call__(self, obj):
        try:
            return self.id_map[id(obj)]
        except KeyError:
            self.id_seq += 1
            self.id_map[id(obj)] = self.id_seq
            return self.id_seq
