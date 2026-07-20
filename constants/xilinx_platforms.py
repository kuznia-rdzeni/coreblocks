from amaranth.vendor import XilinxPlatform
from amaranth.build import Resource, Attrs, Pins, Clock, PinsN

from constants.platform_utils import PinManager, ResourceBuilder

__all__ = ["make_xc7a200t_platform", "make_xc7k480t_platform"]


xc7a200t_fbg676_pins = """
A2 A3 A4 A5 A7 A9 A11 A13 A17 A18 A19 A20
A22 A23 A24 A25 AA2 AA3 AA4 AA5 AA7 AA8 AA11 AA13
AA15 AA17 AA18 AA19 AA20 AA22 AA23 AA24 AA25 AB1 AB2 AB4
AB5 AB6 AB11 AB13 AB16 AB17 AB19 AB20 AB21 AB22 AB24 AB25
AB26 AC1 AC2 AC3 AC4 AC6 AC8 AC10 AC12 AC14 AC16 AC17
AC18 AC19 AC21 AC22 AC23 AC24 AC26 AD1 AD3 AD4 AD5 AD8
AD10 AD12 AD14 AD17 AD18 AD19 AD20 AD21 AD23 AD24 AD25 AD26
AE1 AE2 AE3 AE5 AE7 AE9 AE11 AE13 AE17 AE18 AE20 AE21
AE22 AE23 AE25 AE26 AF2 AF3 AF4 AF5 AF7 AF9 AF11 AF13
AF17 AF18 AF19 AF20 AF22 AF23 AF24 AF25 B1 B2 B4 B5
B7 B9 B11 B13 B17 B19 B20 B21 B22 B24 B25 B26
C1 C2 C3 C4 C8 C10 C12 C14 C17 C18 C19 C21
C22 C23 C24 C26 D1 D3 D4 D5 D6 D8 D10 D12
D14 D16 D18 D19 D20 D21 D23 D24 D25 D26 E1 E2
E3 E5 E6 E11 E13 E16 E17 E18 E20 E21 E22 E23
E25 E26 F2 F3 F4 F5 F7 F8 F11 F13 F15 F17
F18 F19 F20 F22 F23 F24 F25 G1 G2 G4 G5 G6
G7 G8 G9 G15 G16 G17 G19 G20 G21 G22 G24 G25
G26 H1 H2 H3 H4 H6 H7 H8 H9 H14 H15 H16
H17 H18 H19 H21 H22 H23 H24 H26 J1 J3 J4 J5
J6 J8 J14 J15 J16 J18 J19 J20 J21 J23 J24 J25
J26 K1 K2 K3 K5 K6 K7 K8 K15 K16 K17 K18
K20 K21 K22 K23 K25 K26 L2 L3 L4 L5 L7 L8
L14 L15 L17 L18 L19 L20 L22 L23 L24 L25 M1 M2
M4 M5 M6 M7 M14 M15 M16 M17 M19 M20 M21 M22
M24 M25 M26 N1 N2 N3 N4 N6 N7 N8 N12 N14
N16 N17 N18 N19 N21 N22 N23 N24 N26 P1 P3 P4
P5 P6 P8 P11 P14 P15 P16 P18 P19 P20 P21 P23
P24 P25 P26 R1 R2 R3 R5 R6 R7 R8 R14 R15
R16 R17 R18 R20 R21 R22 R23 R25 R26 T2 T3 T4
T5 T7 T8 T14 T15 T17 T18 T19 T20 T22 T23 T24
T25 U1 U2 U4 U5 U6 U7 U14 U15 U16 U17 U19
U20 U21 U22 U24 U25 U26 V1 V2 V3 V4 V6 V7
V8 V9 V14 V16 V17 V18 V19 V21 V22 V23 V24 V26
W1 W3 W4 W5 W6 W8 W14 W15 W16 W18 W19 W20
W21 W23 W24 W25 W26 Y1 Y2 Y3 Y5 Y6 Y7 Y8
Y15 Y16 Y17 Y18 Y20 Y21 Y22 Y23 Y25 Y26
""".split()
xc7a200t_fbg676_pclk = """
AA2 AA3 AA4 AA19 AA20 AB4 AB19 AB20 C18 C19 D5 D18
D19 E5 F5 G5 H21 H22 J21 K21 M21 M22 N2 N3
N21 N22 P3 R3 U21 U22 V21 V22
""".split()
xc7k480t_ffg1156_pins = """
A3 A4 A7 A8 A11 A12 A16 A18 A19 A20 A21 A23
A24 A25 A26 A28 A29 A30 A31 A33 AA3 AA4 AA7 AA8
AA24 AA25 AA26 AA28 AA29 AA30 AA31 AA33 AA34 AB1 AB2 AB5
AB6 AB25 AB26 AB27 AB28 AB30 AB31 AB32 AB33 AC3 AC4 AC7
AC8 AC24 AC25 AC27 AC28 AC29 AC30 AC32 AC33 AC34 AD1 AD2
AD5 AD6 AD24 AD25 AD26 AD27 AD29 AD30 AD31 AD32 AD34 AE3
AE4 AE24 AE26 AE27 AE28 AE29 AE31 AE32 AE33 AE34 AF1 AF2
AF5 AF6 AF24 AF25 AF26 AF28 AF29 AF30 AF31 AF33 AF34 AG3
AG4 AG7 AG8 AG15 AG16 AG17 AG18 AG20 AG21 AG22 AG23 AG25
AG26 AG27 AG28 AG30 AG31 AG32 AG33 AH1 AH2 AH5 AH6 AH9
AH10 AH17 AH18 AH19 AH20 AH22 AH23 AH24 AH25 AH27 AH28 AH29
AH30 AH32 AH33 AH34 AJ3 AJ4 AJ7 AJ8 AJ11 AJ12 AJ16 AJ17
AJ19 AJ20 AJ21 AJ22 AJ24 AJ25 AJ26 AJ27 AJ29 AJ30 AJ31 AJ32
AJ34 AK1 AK2 AK5 AK6 AK9 AK10 AK16 AK17 AK18 AK19 AK21
AK22 AK23 AK24 AK26 AK27 AK28 AK29 AK31 AK32 AK33 AK34 AL3
AL4 AL7 AL8 AL11 AL12 AL16 AL18 AL19 AL20 AL21 AL23 AL24
AL25 AL26 AL28 AL29 AL30 AL31 AL33 AL34 AM1 AM2 AM5 AM6
AM9 AM10 AM16 AM17 AM18 AM20 AM21 AM22 AM23 AM25 AM26 AM27
AM28 AM30 AM31 AM32 AM33 AN3 AN4 AN7 AN8 AN11 AN12 AN17
AN18 AN19 AN20 AN22 AN23 AN24 AN25 AN27 AN28 AN29 AN30 AN32
AN34 AP1 AP2 AP5 AP6 AP9 AP10 AP16 AP17 AP19 AP20 AP21
AP22 AP24 AP25 AP26 AP27 AP29 AP30 AP31 AP32 AP33 B1 B2
B5 B6 B9 B10 B16 B17 B18 B20 B21 B22 B23 B25
B26 B27 B28 B30 B31 B32 B33 C3 C4 C7 C8 C11
C12 C17 C18 C19 C20 C22 C23 C24 C25 C27 C28 C29
C30 C32 C33 C34 D1 D2 D5 D6 D9 D10 D16 D17
D19 D20 D21 D22 D24 D25 D26 D27 D29 D30 D31 D32
D34 E3 E4 E7 E8 E11 E12 E16 E17 E18 E19 E21
E22 E23 E24 E26 E27 E28 E29 E31 E32 E33 E34 F1
F2 F5 F6 F9 F10 F16 F18 F19 F20 F21 F23 F24
F25 F26 F28 F29 F30 F31 F33 F34 G3 G4 G7 G8
G16 G17 G18 G20 G21 G22 G23 G25 G26 G27 G28 G30
G31 G32 G33 H1 H2 H5 H6 H9 H10 H17 H18 H19
H20 H22 H23 H24 H25 H27 H28 H29 H30 H32 H33 H34
J3 J4 J7 J8 J24 J25 J26 J27 J29 J30 J31 J32
J34 K1 K2 K5 K6 K24 K26 K27 K28 K29 K31 K32
K33 K34 L3 L4 L7 L8 L24 L25 L26 L28 L29 L30
L31 L33 L34 M1 M2 M5 M6 M25 M26 M27 M28 M30
M31 M32 M33 N3 N4 N24 N25 N27 N28 N29 N30 N32
N33 N34 P1 P2 P5 P6 P24 P25 P26 P27 P29 P30
P31 P32 P34 R3 R4 R7 R8 R24 R26 R27 R28 R29
R31 R32 R33 R34 T1 T2 T5 T6 T24 T25 T26 T28
T29 T30 T31 T33 T34 U3 U4 U7 U8 U25 U26
U27 U28 U30 U31 U32 U33 V1 V2 V5 V6 V24
V25 V27 V28 V29 V30 V32 V33 V34 W3 W4 W7 W8
W24 W25 W26 W27 W29 W30 W31 W32 W34 Y1 Y2 Y5
Y6 Y24 Y26 Y27 Y28 Y29 Y31 Y32 Y33 Y34
""".split()
xc7k480t_ffg1156_pclk = """
AA28 AA29 AF31 AG31 AJ26 AJ27 AJ31 AK18 AK19 AK26 AK27 AK31
AL18 AL19 D19 D32 E19 E21 E22 E26 E27 E32 F30 G27
G30 H27 P31 R28 R29 R31 Y26 Y27
""".split()


class XrayXilinxPlatform(XilinxPlatform):
    def __init__(self, *, toolchain="Xray"):
        super().__init__(toolchain=toolchain)

        templates = self._xray_command_templates  # type: ignore
        # Allow synthesis of block RAM
        templates[0] = templates[0].replace("-nobram", "")
        # Don't emit '$scopeinfo' cells
        templates[0] = templates[0].replace("write_json", "write_json -noscopeinfo")
        # Save nextpnr log
        templates[1] += r""" --log {{name}}.tim"""
        # Don't generate bitstream (for now)
        templates.pop()  # type: ignore
        templates.pop()  # type: ignore
        # Fix tcl escaping for nextpnr-xilinx
        templates.insert(1, r"""sed -i "s/\\\\\[/[/" {{name}}.xdc""")
        # Update env for Nix nextpnr-xilinx
        # self._xray_command_templates.insert(1, r""". /etc/nix-devshell-env.sh""")

    @property
    def _xray_device(self):
        # Workaround for chipdb naming
        return f"{super()._xray_device}{self.package}"  # type: ignore


def make_xc7a200t_platform(resource_builder: ResourceBuilder):
    pins = PinManager(xc7a200t_fbg676_pins)

    class XC7A200TPlatform(XrayXilinxPlatform):
        device = "xc7a200t"
        package = "fbg676"
        speed = "2"
        default_clk = "clk"
        default_rst = "rst"

        clk_pin = pins.named_pin(xc7a200t_fbg676_pclk)
        resources = [
            Resource("rst", 0, PinsN(pins.p(), dir="i"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("clk", 0, Pins(clk_pin, dir="i"), Clock(100e6), Attrs(IOSTANDARD="LVCMOS33")),
        ] + resource_builder(pins, attrs=Attrs(IOSTANDARD="LVCMOS33"))

        connectors = []

        def toolchain_program(self, products, name, **kwargs):
            pass

    return XC7A200TPlatform


def make_xc7k480t_platform(resource_builder: ResourceBuilder):
    pins = PinManager(xc7k480t_ffg1156_pins)

    class XC7K480TPlatform(XrayXilinxPlatform):
        device = "xc7k480t"
        package = "ffg1156"
        speed = "2"
        default_clk = "clk"
        default_rst = "rst"

        clk_pin = pins.named_pin(xc7k480t_ffg1156_pclk)
        resources = [
            Resource("rst", 0, PinsN(pins.p(), dir="i"), Attrs(IOSTANDARD="LVCMOS33")),
            Resource("clk", 0, Pins(clk_pin, dir="i"), Clock(100e6), Attrs(IOSTANDARD="LVCMOS33")),
        ] + resource_builder(pins, attrs=Attrs(IOSTANDARD="LVCMOS33"))

        connectors = []

        @property
        def _xray_family(self):
            # Upstream Amaranth's Xray backend only maps xc7a -> artix7 and
            # xc7z -> zynq7. openXC7 extends prjxray-db coverage to Kintex-7,
            # so teach this platform about "xc7k" parts too.
            if self.device[:4] == "xc7k":
                return "kintex7"
            return super()._xray_family  # type: ignore

        def toolchain_program(self, products, name, **kwargs):
            pass

    return XC7K480TPlatform
