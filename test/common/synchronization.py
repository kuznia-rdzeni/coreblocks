from amaranth.sim import Settle


class CondVar:
    """
    Simple CondVar. It has some limitations e.g. it can not notify other process
    without waiting a cycle.
    """

    def __init__(self, notify_prio: bool = False, transparent: bool = True):
        self.var = False
        self.notify_prio = notify_prio
        self.transparent = transparent

    def wait(self):
        yield Settle()
        if not self.transparent:
            yield Settle()
        while not self.var:
            yield
            yield Settle()
        if self.notify_prio:
            yield Settle()
            yield Settle()

    def notify_all(self):
        # We need to wait a cycle because we have a race between notify and wait
        # waiting process could already call the `yield` so it would skip our notification
        yield
        self.var = True
        yield Settle()
        yield Settle()
        self.var = False
