from amaranth import Record, Signal, Elaboratable
from amaranth.hdl.rec import Layout
from transactions import *
from typing import Generic, type_check_only, TypeVar, Literal

L = TypeVar('L')

@type_check_only
class RecordType(Generic[L], Record):
#    def __getattr__(self, name: L) -> Signal:   <-- Nie działa
    def __getattr__(self, name: str) -> Signal:
        pass

class RSRowParam:
    opcode_width = 4
    id_reg_width = 5
    id_ROB_width = 6
    val_width = 32
    position_width = 4

    insert_layout = Layout([
        ("opcode", opcode_width),
        ("id_rs1", id_reg_width),
        ("id_rs2", id_reg_width),
        ("id_out", id_reg_width),
        ("id_ROB", id_ROB_width),
        ("position", position_width)
        ])

class RSRowInnerData:
    def __init__(self, params : RSRowParam):
        self.params = params

        self.valid = Signal()
        self.opcode = Signal(self.params.opcode_width)
        self.id_rs1 = Signal(self.params.id_reg_width)
        self.id_rs2 = Signal(self.params.id_reg_width)
        self.id_out = Signal(self.params.id_reg_width)
        self.id_ROB = Signal(self.params.id_ROB_width)
        self.val_rs1 = Signal(self.params.val_width)
        self.val_rs2 = Signal(self.params.val_width)
        

class RSRow(Elaboratable):
    def __init__(self, params : RSRowParam):
        self.params = params
        self.m_insert = Method(i=params.insert_layout)

        self._inner_data : RSRowInnerData = RSRowInnerData(params)

    def elaborate(self):
        m = Module()

        with self.m_insert.when_called(m) as arg:
            self.method_insert(arg)
        return m

    def method_insert(self, arg : RecordType[Literal["nazwa", "smok"]] ):
        test : Signal = arg.smokZimny
