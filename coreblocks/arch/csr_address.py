from amaranth.lib.enum import IntEnum, unique

__all__ = ["CSRAddress", "MstatusFieldOffsets"]


@unique
class CSRAddress(IntEnum, shape=12):
    # Unprivileged Floating-Point CSRs
    FFLAGS = 0x001  # Floating-Point Accrued Exceptions
    FRM = 0x002  # Floating-Point Dynamic Rounding Mode
    FCSR = 0x003  # Floating-Point Control and Status Register (`frm` +`fflags`)

    # Unprivileged Zicfiss extension CSR
    SSP = 0x011  # Shadow Stack Pointer

    # Unprivileged Counter/Timers
    CYCLE = 0xC00  # Cycle counter for RDCYCLE instruction
    TIME = 0xC01  # Timer for RDTIME instruction
    INSTRET = 0xC02  # Instructions-retired counter for RDINSTRET instruction
    HPMCOUNTER3 = 0xC03  # Performance-monitoring counter
    HPMCOUNTER4 = 0xC04  # Performance-monitoring counter
    HPMCOUNTER5 = 0xC05  # Performance-monitoring counter
    HPMCOUNTER6 = 0xC06  # Performance-monitoring counter
    HPMCOUNTER7 = 0xC07  # Performance-monitoring counter
    HPMCOUNTER8 = 0xC08  # Performance-monitoring counter
    HPMCOUNTER9 = 0xC09  # Performance-monitoring counter
    HPMCOUNTER10 = 0xC0A  # Performance-monitoring counter
    HPMCOUNTER11 = 0xC0B  # Performance-monitoring counter
    HPMCOUNTER12 = 0xC0C  # Performance-monitoring counter
    HPMCOUNTER13 = 0xC0D  # Performance-monitoring counter
    HPMCOUNTER14 = 0xC0E  # Performance-monitoring counter
    HPMCOUNTER15 = 0xC0F  # Performance-monitoring counter
    HPMCOUNTER16 = 0xC10  # Performance-monitoring counter
    HPMCOUNTER17 = 0xC11  # Performance-monitoring counter
    HPMCOUNTER18 = 0xC12  # Performance-monitoring counter
    HPMCOUNTER19 = 0xC13  # Performance-monitoring counter
    HPMCOUNTER20 = 0xC14  # Performance-monitoring counter
    HPMCOUNTER21 = 0xC15  # Performance-monitoring counter
    HPMCOUNTER22 = 0xC16  # Performance-monitoring counter
    HPMCOUNTER23 = 0xC17  # Performance-monitoring counter
    HPMCOUNTER24 = 0xC18  # Performance-monitoring counter
    HPMCOUNTER25 = 0xC19  # Performance-monitoring counter
    HPMCOUNTER26 = 0xC1A  # Performance-monitoring counter
    HPMCOUNTER27 = 0xC1B  # Performance-monitoring counter
    HPMCOUNTER28 = 0xC1C  # Performance-monitoring counter
    HPMCOUNTER29 = 0xC1D  # Performance-monitoring counter
    HPMCOUNTER30 = 0xC1E  # Performance-monitoring counter
    HPMCOUNTER31 = 0xC1F  # Performance-monitoring counter
    CYCLEH = 0xC80  # Upper 32 bits of `cycle`, RV32 only
    TIMEH = 0xC81  # Upper 32 bits of `time`, RV32 only
    INSTRETH = 0xC82  # Upper 32 bits of `instret`, RV32 only
    HPMCOUNTER3H = 0xC83  # Upper 32 bits of `hpmcounter3`, RV32 only
    HPMCOUNTER4H = 0xC84  # Upper 32 bits of `hpmcounter4`, RV32 only
    HPMCOUNTER5H = 0xC85  # Upper 32 bits of `hpmcounter5`, RV32 only
    HPMCOUNTER6H = 0xC86  # Upper 32 bits of `hpmcounter6`, RV32 only
    HPMCOUNTER7H = 0xC87  # Upper 32 bits of `hpmcounter7`, RV32 only
    HPMCOUNTER8H = 0xC88  # Upper 32 bits of `hpmcounter8`, RV32 only
    HPMCOUNTER9H = 0xC89  # Upper 32 bits of `hpmcounter9`, RV32 only
    HPMCOUNTER10H = 0xC8A  # Upper 32 bits of `hpmcounter10`, RV32 only
    HPMCOUNTER11H = 0xC8B  # Upper 32 bits of `hpmcounter11`, RV32 only
    HPMCOUNTER12H = 0xC8C  # Upper 32 bits of `hpmcounter12`, RV32 only
    HPMCOUNTER13H = 0xC8D  # Upper 32 bits of `hpmcounter13`, RV32 only
    HPMCOUNTER14H = 0xC8E  # Upper 32 bits of `hpmcounter14`, RV32 only
    HPMCOUNTER15H = 0xC8F  # Upper 32 bits of `hpmcounter15`, RV32 only
    HPMCOUNTER16H = 0xC90  # Upper 32 bits of `hpmcounter16`, RV32 only
    HPMCOUNTER17H = 0xC91  # Upper 32 bits of `hpmcounter17`, RV32 only
    HPMCOUNTER18H = 0xC92  # Upper 32 bits of `hpmcounter18`, RV32 only
    HPMCOUNTER19H = 0xC93  # Upper 32 bits of `hpmcounter19`, RV32 only
    HPMCOUNTER20H = 0xC94  # Upper 32 bits of `hpmcounter20`, RV32 only
    HPMCOUNTER21H = 0xC95  # Upper 32 bits of `hpmcounter21`, RV32 only
    HPMCOUNTER22H = 0xC96  # Upper 32 bits of `hpmcounter22`, RV32 only
    HPMCOUNTER23H = 0xC97  # Upper 32 bits of `hpmcounter23`, RV32 only
    HPMCOUNTER24H = 0xC98  # Upper 32 bits of `hpmcounter24`, RV32 only
    HPMCOUNTER25H = 0xC99  # Upper 32 bits of `hpmcounter25`, RV32 only
    HPMCOUNTER26H = 0xC9A  # Upper 32 bits of `hpmcounter26`, RV32 only
    HPMCOUNTER27H = 0xC9B  # Upper 32 bits of `hpmcounter27`, RV32 only
    HPMCOUNTER28H = 0xC9C  # Upper 32 bits of `hpmcounter28`, RV32 only
    HPMCOUNTER29H = 0xC9D  # Upper 32 bits of `hpmcounter29`, RV32 only
    HPMCOUNTER30H = 0xC9E  # Upper 32 bits of `hpmcounter30`, RV32 only
    HPMCOUNTER31H = 0xC9F  # Upper 32 bits of `hpmcounter31`, RV32 only

    # Supervisor Trap Setup
    SSTATUS = 0x100  # Supervisor status register
    SIE = 0x104  # Supervisor interrupt-enable register
    STVEC = 0x105  # Supervisor trap handler base address
    SCOUNTEREN = 0x106  # Supervisor counter enable

    # Supervisor Configuration
    SENVCFG = 0x10A  # Supervisor environment configuration register

    # Supervisor Counter Setup
    SCOUNTINHIBIT = 0x120  # Supervisor counter-inhibit register

    # Supervisor Trap Handling
    SSCRATCH = 0x140  # Scratch register for supervisor trap handlers
    SEPC = 0x141  # Supervisor exception program counter
    SCAUSE = 0x142  # Supervisor trap cause
    STVAL = 0x143  # Supervisor bad address or instruction
    SIP = 0x144  # Supervisor interrupt pending
    SCOUNTOVF = 0xDA0  # Supervisor count overflow

    # Supervisor Protection and Translation
    SATP = 0x180  # Supervisor address translation and protection

    # Debug/Trace Registers
    SCONTEXT = 0x5A8  # Supervisor-mode context register

    # Supervisor State Enable Registers
    SSTATEEN0 = 0x10C  # Supervisor State Enable 0 Register
    SSTATEEN1 = 0x10D  # Supervisor State Enable 1 Register
    SSTATEEN2 = 0x10E  # Supervisor State Enable 2 Register
    SSTATEEN3 = 0x10F  # Supervisor State Enable 3 Register

    # Hypervisor Trap Setup
    HSTATUS = 0x600  # Hypervisor status register
    HEDELEG = 0x602  # Hypervisor exception delegation register
    HIDELEG = 0x603  # Hypervisor interrupt delegation register
    HIE = 0x604  # Hypervisor interrupt-enable register
    HCOUNTEREN = 0x606  # Hypervisor counter enable
    HGEIE = 0x607  # Hypervisor guest external interrupt-enable register
    HEDELEGH = 0x612  # Upper 32 bits of `hedeleg`, RV32 only

    # Hypervisor Trap Handling
    HTVAL = 0x643  # Hypervisor bad guest physical address
    HIP = 0x644  # Hypervisor interrupt pending
    HVIP = 0x645  # Hypervisor virtual interrupt pending
    HTINST = 0x64A  # Hypervisor trap instruction (transformed)
    HGEIP = 0xE12  # Hypervisor guest external interrupt pending

    # Hypervisor Configuration
    HENVCFG = 0x60A  # Hypervisor environment configuration register
    HENVCFGH = 0x61A  # Upper 32 bits of `henvcfg`, RV32 only

    # Hypervisor Protection and Translation
    HGATP = 0x680  # Hypervisor guest address translation and protection

    # Debug/Trace Registers
    HCONTEXT = 0x6A8  # Hypervisor-mode context register

    # Hypervisor Counter/Timer Virtualization Registers
    HTIMEDELTA = 0x605  # Delta for VS/VU-mode timer
    HTIMEDELTAH = 0x615  # Upper 32 bits of `htimedelta`, RV32 only

    # Hypervisor State Enable Registers
    HSTATEEN0 = 0x60C  # Hypervisor State Enable 0 Register
    HSTATEEN1 = 0x60D  # Hypervisor State Enable 1 Register
    HSTATEEN2 = 0x60E  # Hypervisor State Enable 2 Register
    HSTATEEN3 = 0x60F  # Hypervisor State Enable 3 Register
    HSTATEEN0H = 0x61C  # Upper 32 bits of Hypervisor State Enable 0 Register, RV32 only
    HSTATEEN1H = 0x61D  # Upper 32 bits of Hypervisor State Enable 1 Register, RV32 only
    HSTATEEN2H = 0x61E  # Upper 32 bits of Hypervisor State Enable 2 Register, RV32 only
    HSTATEEN3H = 0x61F  # Upper 32 bits of Hypervisor State Enable 3 Register, RV32 only

    # Virtual Supervisor Registers
    VSSTATUS = 0x200  # Virtual supervisor status register
    VSIE = 0x204  # Virtual supervisor interrupt-enable register
    VSTVEC = 0x205  # Virtual supervisor trap handler base address
    VSSCRATCH = 0x240  # Virtual supervisor scratch register
    VSEPC = 0x241  # Virtual supervisor exception program counter
    VSCAUSE = 0x242  # Virtual supervisor trap cause
    VSTVAL = 0x243  # Virtual supervisor bad address or instruction
    VSIP = 0x244  # Virtual supervisor interrupt pending
    VSATP = 0x280  # Virtual supervisor address translation and protection

    # Machine Information Registers
    MVENDORID = 0xF11  # Vendor ID
    MARCHID = 0xF12  # Architecture ID
    MIMPID = 0xF13  # Implementation ID
    MHARTID = 0xF14  # Hardware thread ID
    MCONFIGPTR = 0xF15  # Pointer to configuration data structure

    # Machine Trap Setup
    MSTATUS = 0x300  # Machine status register
    MISA = 0x301  # ISA and extension
    MEDELEG = 0x302  # Machine exception delegation register
    MIDELEG = 0x303  # Machine interrupt delegation register
    MIE = 0x304  # Machine interrupt-enable register
    MTVEC = 0x305  # Machine trap-handler base address
    MCOUNTEREN = 0x306  # Machine counter enable
    MSTATUSH = 0x310  # Additional machine status register, RV32 only
    MEDELEGH = 0x312  # Upper 32 bits of `medeleg`, RV32 only

    # Machine Trap Handling
    MSCRATCH = 0x340  # Scratch register for machine trap handlers
    MEPC = 0x341  # Machine exception program counter
    MCAUSE = 0x342  # Machine trap cause
    MTVAL = 0x343  # Machine bad address or instruction
    MIP = 0x344  # Machine interrupt pending
    MTINST = 0x34A  # Machine trap instruction (transformed)
    MTVAL2 = 0x34B  # Machine bad guest physical address

    # Machine Configuration
    MENVCFG = 0x30A  # Machine environment configuration register
    MENVCFGH = 0x31A  # Upper 32 bits of `menvcfg`, RV32 only
    MSECCFG = 0x747  # Machine security configuration register
    MSECCFGH = 0x757  # Upper 32 bits of `mseccfg`, RV32 only

    # Machine Memory Protection
    PMPCFG0 = 0x3A0  # Physical memory protection configuration
    PMPCFG1 = 0x3A1  # Physical memory protection configuration, RV32 only
    PMPCFG2 = 0x3A2  # Physical memory protection configuration
    PMPCFG3 = 0x3A3  # Physical memory protection configuration, RV32 only
    PMPCFG4 = 0x3A4  # Physical memory protection configuration
    PMPCFG5 = 0x3A5  # Physical memory protection configuration, RV32 only
    PMPCFG6 = 0x3A6  # Physical memory protection configuration
    PMPCFG7 = 0x3A7  # Physical memory protection configuration, RV32 only
    PMPCFG8 = 0x3A8  # Physical memory protection configuration
    PMPCFG9 = 0x3A9  # Physical memory protection configuration, RV32 only
    PMPCFG10 = 0x3AA  # Physical memory protection configuration
    PMPCFG11 = 0x3AB  # Physical memory protection configuration, RV32 only
    PMPCFG12 = 0x3AC  # Physical memory protection configuration
    PMPCFG13 = 0x3AD  # Physical memory protection configuration, RV32 only
    PMPCFG14 = 0x3AE  # Physical memory protection configuration
    PMPCFG15 = 0x3AF  # Physical memory protection configuration, RV32 only
    PMPADDR0 = 0x3B0  # Physical memory protection address register
    PMPADDR1 = 0x3B1  # Physical memory protection address register
    PMPADDR2 = 0x3B2  # Physical memory protection address register
    PMPADDR3 = 0x3B3  # Physical memory protection address register
    PMPADDR4 = 0x3B4  # Physical memory protection address register
    PMPADDR5 = 0x3B5  # Physical memory protection address register
    PMPADDR6 = 0x3B6  # Physical memory protection address register
    PMPADDR7 = 0x3B7  # Physical memory protection address register
    PMPADDR8 = 0x3B8  # Physical memory protection address register
    PMPADDR9 = 0x3B9  # Physical memory protection address register
    PMPADDR10 = 0x3BA  # Physical memory protection address register
    PMPADDR11 = 0x3BB  # Physical memory protection address register
    PMPADDR12 = 0x3BC  # Physical memory protection address register
    PMPADDR13 = 0x3BD  # Physical memory protection address register
    PMPADDR14 = 0x3BE  # Physical memory protection address register
    PMPADDR15 = 0x3BF  # Physical memory protection address register
    PMPADDR16 = 0x3C0  # Physical memory protection address register
    PMPADDR17 = 0x3C1  # Physical memory protection address register
    PMPADDR18 = 0x3C2  # Physical memory protection address register
    PMPADDR19 = 0x3C3  # Physical memory protection address register
    PMPADDR20 = 0x3C4  # Physical memory protection address register
    PMPADDR21 = 0x3C5  # Physical memory protection address register
    PMPADDR22 = 0x3C6  # Physical memory protection address register
    PMPADDR23 = 0x3C7  # Physical memory protection address register
    PMPADDR24 = 0x3C8  # Physical memory protection address register
    PMPADDR25 = 0x3C9  # Physical memory protection address register
    PMPADDR26 = 0x3CA  # Physical memory protection address register
    PMPADDR27 = 0x3CB  # Physical memory protection address register
    PMPADDR28 = 0x3CC  # Physical memory protection address register
    PMPADDR29 = 0x3CD  # Physical memory protection address register
    PMPADDR30 = 0x3CE  # Physical memory protection address register
    PMPADDR31 = 0x3CF  # Physical memory protection address register
    PMPADDR32 = 0x3D0  # Physical memory protection address register
    PMPADDR33 = 0x3D1  # Physical memory protection address register
    PMPADDR34 = 0x3D2  # Physical memory protection address register
    PMPADDR35 = 0x3D3  # Physical memory protection address register
    PMPADDR36 = 0x3D4  # Physical memory protection address register
    PMPADDR37 = 0x3D5  # Physical memory protection address register
    PMPADDR38 = 0x3D6  # Physical memory protection address register
    PMPADDR39 = 0x3D7  # Physical memory protection address register
    PMPADDR40 = 0x3D8  # Physical memory protection address register
    PMPADDR41 = 0x3D9  # Physical memory protection address register
    PMPADDR42 = 0x3DA  # Physical memory protection address register
    PMPADDR43 = 0x3DB  # Physical memory protection address register
    PMPADDR44 = 0x3DC  # Physical memory protection address register
    PMPADDR45 = 0x3DD  # Physical memory protection address register
    PMPADDR46 = 0x3DE  # Physical memory protection address register
    PMPADDR47 = 0x3DF  # Physical memory protection address register
    PMPADDR48 = 0x3E0  # Physical memory protection address register
    PMPADDR49 = 0x3E1  # Physical memory protection address register
    PMPADDR50 = 0x3E2  # Physical memory protection address register
    PMPADDR51 = 0x3E3  # Physical memory protection address register
    PMPADDR52 = 0x3E4  # Physical memory protection address register
    PMPADDR53 = 0x3E5  # Physical memory protection address register
    PMPADDR54 = 0x3E6  # Physical memory protection address register
    PMPADDR55 = 0x3E7  # Physical memory protection address register
    PMPADDR56 = 0x3E8  # Physical memory protection address register
    PMPADDR57 = 0x3E9  # Physical memory protection address register
    PMPADDR58 = 0x3EA  # Physical memory protection address register
    PMPADDR59 = 0x3EB  # Physical memory protection address register
    PMPADDR60 = 0x3EC  # Physical memory protection address register
    PMPADDR61 = 0x3ED  # Physical memory protection address register
    PMPADDR62 = 0x3EE  # Physical memory protection address register
    PMPADDR63 = 0x3EF  # Physical memory protection address register

    # Machine State Enable Registers
    MSTATEEN0 = 0x30C  # Machine State Enable 0 Register
    MSTATEEN1 = 0x30D  # Machine State Enable 1 Register
    MSTATEEN2 = 0x30E  # Machine State Enable 2 Register
    MSTATEEN3 = 0x30F  # Machine State Enable 3 Register
    MSTATEEN0H = 0x31C  # Upper 32 bits of Machine State Enable 0 Register, RV32 only
    MSTATEEN1H = 0x31D  # Upper 32 bits of Machine State Enable 1 Register, RV32 only
    MSTATEEN2H = 0x31E  # Upper 32 bits of Machine State Enable 2 Register, RV32 only
    MSTATEEN3H = 0x31F  # Upper 32 bits of Machine State Enable 3 Register, RV32 only

    # Machine Non-Maskable Interrupt Handling
    MNSCRATCH = 0x740  # Resumable NMI scratch register
    MNEPC = 0x741  # Resumable NMI program counter
    MNCAUSE = 0x742  # Resumable NMI cause
    MNSTATUS = 0x744  # Resumable NMI status

    # Machine Counter/Timers
    MCYCLE = 0xB00  # Machine cycle counter
    MINSTRET = 0xB02  # Machine instructions-retired counter
    MHPMCOUNTER3 = 0xB03  # Machine performance-monitoring counter
    MHPMCOUNTER4 = 0xB04  # Machine performance-monitoring counter
    MHPMCOUNTER5 = 0xB05  # Machine performance-monitoring counter
    MHPMCOUNTER6 = 0xB06  # Machine performance-monitoring counter
    MHPMCOUNTER7 = 0xB07  # Machine performance-monitoring counter
    MHPMCOUNTER8 = 0xB08  # Machine performance-monitoring counter
    MHPMCOUNTER9 = 0xB09  # Machine performance-monitoring counter
    MHPMCOUNTER10 = 0xB0A  # Machine performance-monitoring counter
    MHPMCOUNTER11 = 0xB0B  # Machine performance-monitoring counter
    MHPMCOUNTER12 = 0xB0C  # Machine performance-monitoring counter
    MHPMCOUNTER13 = 0xB0D  # Machine performance-monitoring counter
    MHPMCOUNTER14 = 0xB0E  # Machine performance-monitoring counter
    MHPMCOUNTER15 = 0xB0F  # Machine performance-monitoring counter
    MHPMCOUNTER16 = 0xB10  # Machine performance-monitoring counter
    MHPMCOUNTER17 = 0xB11  # Machine performance-monitoring counter
    MHPMCOUNTER18 = 0xB12  # Machine performance-monitoring counter
    MHPMCOUNTER19 = 0xB13  # Machine performance-monitoring counter
    MHPMCOUNTER20 = 0xB14  # Machine performance-monitoring counter
    MHPMCOUNTER21 = 0xB15  # Machine performance-monitoring counter
    MHPMCOUNTER22 = 0xB16  # Machine performance-monitoring counter
    MHPMCOUNTER23 = 0xB17  # Machine performance-monitoring counter
    MHPMCOUNTER24 = 0xB18  # Machine performance-monitoring counter
    MHPMCOUNTER25 = 0xB19  # Machine performance-monitoring counter
    MHPMCOUNTER26 = 0xB1A  # Machine performance-monitoring counter
    MHPMCOUNTER27 = 0xB1B  # Machine performance-monitoring counter
    MHPMCOUNTER28 = 0xB1C  # Machine performance-monitoring counter
    MHPMCOUNTER29 = 0xB1D  # Machine performance-monitoring counter
    MHPMCOUNTER30 = 0xB1E  # Machine performance-monitoring counter
    MHPMCOUNTER31 = 0xB1F  # Machine performance-monitoring counter
    MCYCLEH = 0xB80  # Upper 32 bits of `mcycle`, RV32 only
    MINSTRETH = 0xB82  # Upper 32 bits of `minstret`, RV32 only
    MHPMCOUNTER3H = 0xB83  # Upper 32 bits of `mhpmcounter3`, RV32 only
    MHPMCOUNTER4H = 0xB84  # Upper 32 bits of `mhpmcounter4`, RV32 only
    MHPMCOUNTER5H = 0xB85  # Upper 32 bits of `mhpmcounter5`, RV32 only
    MHPMCOUNTER6H = 0xB86  # Upper 32 bits of `mhpmcounter6`, RV32 only
    MHPMCOUNTER7H = 0xB87  # Upper 32 bits of `mhpmcounter7`, RV32 only
    MHPMCOUNTER8H = 0xB88  # Upper 32 bits of `mhpmcounter8`, RV32 only
    MHPMCOUNTER9H = 0xB89  # Upper 32 bits of `mhpmcounter9`, RV32 only
    MHPMCOUNTER10H = 0xB8A  # Upper 32 bits of `mhpmcounter10`, RV32 only
    MHPMCOUNTER11H = 0xB8B  # Upper 32 bits of `mhpmcounter11`, RV32 only
    MHPMCOUNTER12H = 0xB8C  # Upper 32 bits of `mhpmcounter12`, RV32 only
    MHPMCOUNTER13H = 0xB8D  # Upper 32 bits of `mhpmcounter13`, RV32 only
    MHPMCOUNTER14H = 0xB8E  # Upper 32 bits of `mhpmcounter14`, RV32 only
    MHPMCOUNTER15H = 0xB8F  # Upper 32 bits of `mhpmcounter15`, RV32 only
    MHPMCOUNTER16H = 0xB90  # Upper 32 bits of `mhpmcounter16`, RV32 only
    MHPMCOUNTER17H = 0xB91  # Upper 32 bits of `mhpmcounter17`, RV32 only
    MHPMCOUNTER18H = 0xB92  # Upper 32 bits of `mhpmcounter18`, RV32 only
    MHPMCOUNTER19H = 0xB93  # Upper 32 bits of `mhpmcounter19`, RV32 only
    MHPMCOUNTER20H = 0xB94  # Upper 32 bits of `mhpmcounter20`, RV32 only
    MHPMCOUNTER21H = 0xB95  # Upper 32 bits of `mhpmcounter21`, RV32 only
    MHPMCOUNTER22H = 0xB96  # Upper 32 bits of `mhpmcounter22`, RV32 only
    MHPMCOUNTER23H = 0xB97  # Upper 32 bits of `mhpmcounter23`, RV32 only
    MHPMCOUNTER24H = 0xB98  # Upper 32 bits of `mhpmcounter24`, RV32 only
    MHPMCOUNTER25H = 0xB99  # Upper 32 bits of `mhpmcounter25`, RV32 only
    MHPMCOUNTER26H = 0xB9A  # Upper 32 bits of `mhpmcounter26`, RV32 only
    MHPMCOUNTER27H = 0xB9B  # Upper 32 bits of `mhpmcounter27`, RV32 only
    MHPMCOUNTER28H = 0xB9C  # Upper 32 bits of `mhpmcounter28`, RV32 only
    MHPMCOUNTER29H = 0xB9D  # Upper 32 bits of `mhpmcounter29`, RV32 only
    MHPMCOUNTER30H = 0xB9E  # Upper 32 bits of `mhpmcounter30`, RV32 only
    MHPMCOUNTER31H = 0xB9F  # Upper 32 bits of `mhpmcounter31`, RV32 only

    # Machine Counter Setup
    MCOUNTINHIBIT = 0x320  # Machine counter-inhibit register
    MHPMEVENT3 = 0x323  # Machine performance-monitoring event selector
    MHPMEVENT4 = 0x324  # Machine performance-monitoring event selector
    MHPMEVENT5 = 0x325  # Machine performance-monitoring event selector
    MHPMEVENT6 = 0x326  # Machine performance-monitoring event selector
    MHPMEVENT7 = 0x327  # Machine performance-monitoring event selector
    MHPMEVENT8 = 0x328  # Machine performance-monitoring event selector
    MHPMEVENT9 = 0x329  # Machine performance-monitoring event selector
    MHPMEVENT10 = 0x32A  # Machine performance-monitoring event selector
    MHPMEVENT11 = 0x32B  # Machine performance-monitoring event selector
    MHPMEVENT12 = 0x32C  # Machine performance-monitoring event selector
    MHPMEVENT13 = 0x32D  # Machine performance-monitoring event selector
    MHPMEVENT14 = 0x32E  # Machine performance-monitoring event selector
    MHPMEVENT15 = 0x32F  # Machine performance-monitoring event selector
    MHPMEVENT16 = 0x330  # Machine performance-monitoring event selector
    MHPMEVENT17 = 0x331  # Machine performance-monitoring event selector
    MHPMEVENT18 = 0x332  # Machine performance-monitoring event selector
    MHPMEVENT19 = 0x333  # Machine performance-monitoring event selector
    MHPMEVENT20 = 0x334  # Machine performance-monitoring event selector
    MHPMEVENT21 = 0x335  # Machine performance-monitoring event selector
    MHPMEVENT22 = 0x336  # Machine performance-monitoring event selector
    MHPMEVENT23 = 0x337  # Machine performance-monitoring event selector
    MHPMEVENT24 = 0x338  # Machine performance-monitoring event selector
    MHPMEVENT25 = 0x339  # Machine performance-monitoring event selector
    MHPMEVENT26 = 0x33A  # Machine performance-monitoring event selector
    MHPMEVENT27 = 0x33B  # Machine performance-monitoring event selector
    MHPMEVENT28 = 0x33C  # Machine performance-monitoring event selector
    MHPMEVENT29 = 0x33D  # Machine performance-monitoring event selector
    MHPMEVENT30 = 0x33E  # Machine performance-monitoring event selector
    MHPMEVENT31 = 0x33F  # Machine performance-monitoring event selector
    MHPMEVENT3H = 0x723  # Upper 32 bits of `mhpmevent3`, RV32 only
    MHPMEVENT4H = 0x724  # Upper 32 bits of `mhpmevent4`, RV32 only
    MHPMEVENT5H = 0x725  # Upper 32 bits of `mhpmevent5`, RV32 only
    MHPMEVENT6H = 0x726  # Upper 32 bits of `mhpmevent6`, RV32 only
    MHPMEVENT7H = 0x727  # Upper 32 bits of `mhpmevent7`, RV32 only
    MHPMEVENT8H = 0x728  # Upper 32 bits of `mhpmevent8`, RV32 only
    MHPMEVENT9H = 0x729  # Upper 32 bits of `mhpmevent9`, RV32 only
    MHPMEVENT10H = 0x72A  # Upper 32 bits of `mhpmevent10`, RV32 only
    MHPMEVENT11H = 0x72B  # Upper 32 bits of `mhpmevent11`, RV32 only
    MHPMEVENT12H = 0x72C  # Upper 32 bits of `mhpmevent12`, RV32 only
    MHPMEVENT13H = 0x72D  # Upper 32 bits of `mhpmevent13`, RV32 only
    MHPMEVENT14H = 0x72E  # Upper 32 bits of `mhpmevent14`, RV32 only
    MHPMEVENT15H = 0x72F  # Upper 32 bits of `mhpmevent15`, RV32 only
    MHPMEVENT16H = 0x730  # Upper 32 bits of `mhpmevent16`, RV32 only
    MHPMEVENT17H = 0x731  # Upper 32 bits of `mhpmevent17`, RV32 only
    MHPMEVENT18H = 0x732  # Upper 32 bits of `mhpmevent18`, RV32 only
    MHPMEVENT19H = 0x733  # Upper 32 bits of `mhpmevent19`, RV32 only
    MHPMEVENT20H = 0x734  # Upper 32 bits of `mhpmevent20`, RV32 only
    MHPMEVENT21H = 0x735  # Upper 32 bits of `mhpmevent21`, RV32 only
    MHPMEVENT22H = 0x736  # Upper 32 bits of `mhpmevent22`, RV32 only
    MHPMEVENT23H = 0x737  # Upper 32 bits of `mhpmevent23`, RV32 only
    MHPMEVENT24H = 0x738  # Upper 32 bits of `mhpmevent24`, RV32 only
    MHPMEVENT25H = 0x739  # Upper 32 bits of `mhpmevent25`, RV32 only
    MHPMEVENT26H = 0x73A  # Upper 32 bits of `mhpmevent26`, RV32 only
    MHPMEVENT27H = 0x73B  # Upper 32 bits of `mhpmevent27`, RV32 only
    MHPMEVENT28H = 0x73C  # Upper 32 bits of `mhpmevent28`, RV32 only
    MHPMEVENT29H = 0x73D  # Upper 32 bits of `mhpmevent29`, RV32 only
    MHPMEVENT30H = 0x73E  # Upper 32 bits of `mhpmevent30`, RV32 only
    MHPMEVENT31H = 0x73F  # Upper 32 bits of `mhpmevent31`, RV32 only

    # Debug/Trace Registers (shared with Debug Mode)
    TSELECT = 0x7A0  # Debug/Trace trigger register select
    TDATA1 = 0x7A1  # First Debug/Trace trigger data register
    TDATA2 = 0x7A2  # Second Debug/Trace trigger data register
    TDATA3 = 0x7A3  # Third Debug/Trace trigger data register
    MCONTEXT = 0x7A8  # Machine-mode context register

    # Debug Mode Registers
    DCSR = 0x7B0  # Debug control and status register
    DPC = 0x7B1  # Debug program counter
    DSCRATCH0 = 0x7B2  # Debug scratch register 0
    DSCRATCH1 = 0x7B3  # Debug scratch register 1.

    # Internal Coreblocks CSRs
    # used only for testbench verification

    # CSR for custom communication with testbenches
    COREBLOCKS_TEST_CSR = 0x7FF
    # CSR providing writable current privilege mode (U-mode accesible)
    COREBLOCKS_TEST_PRIV_MODE = 0x8FF


@unique
class MstatusFieldOffsets(IntEnum):
    SIE = 1  # Supervisor Interrupt Enable
    MIE = 3  # Machine Interrupt Enable
    SPIE = 5  # Supervisor Previous Interrupt Enable
    UBE = 6  # User Endianess Control
    MPIE = 7  # Machine Previous Interrupt Enable
    SPP = 8  # Supervisor Previous Pirvilege
    VS = 9  # Vector Context Status
    MPP = 11  # Machine Previous Pirvilege
    FS = 13  # Float Context Status
    XS = 15  # Additional Extension State Context Status
    MPRV = 17  # Modify Pirvilege
    SUM = 18  # Supervisor User Memory Access
    MXR = 19  # Make Executable Readable
    TVM = 20  # Trap Virtual Memory
    TW = 21  # Timeout Wait
    TSR = 22  # Trap SRET
    UXL = 32  # User XLEN
    SXL = 34  # Supervisor XLEN
    SBE = 36  # Supervisor Endianess Control
    MBE = 37  # Machine Endianess Contorol
    SD = -1  # Context Status Dirty bit. Placed on last bit of mstatus
