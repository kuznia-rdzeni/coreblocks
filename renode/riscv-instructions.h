#ifndef RISCV_INSTRUCTIONS_H
#define RISCV_INSTRUCTIONS_H

#include <cstdint>

class RiscVInstructions
{
public:
    static uint32_t sw(uint32_t rs2, uint32_t offset, uint32_t rs1)
    {
        /*
        sw rs2, offset(rs1)

        31     25 | 24 20 | 19 15 | 14  12 | 11     7 | 6    0
        imm[11:5] |  rs2  |  rs1  | funct3 | imm[4:0] | opcode

        funct3 = 010
        opcode = 010 0011
        */

        return 0x23 /*opcode*/ | (0x2 << 12) /*funct3*/ | ((rs2 & 0x1f) << 20) | ((rs1 & 0x1f) << 15) | (offset >> 5 << 25) | ((offset & 0xf) << 7);
    }

    static uint32_t csrrs(uint32_t rd, uint32_t csr, uint32_t rs1)
    {
        /*
        csrrw rd, csr, rs1

        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        csr   |  rs1  | funct3 |  rd  | opcode

        funct3 = 010
        opcode = 111 0011
        */

        return 0x73 /*opcode*/ | (0x2 << 12) /*funct3*/ | (csr << 20) | ((rs1 & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static uint32_t csrrw(uint32_t rd, uint32_t csr, uint32_t rs1)
    {
        /*
        csrrw rd, csr, rs1

        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        csr   |  rs1  | funct3 |  rd  | opcode

        funct3 = 010
        opcode = 111 0011
        */

        return 0x73 /*opcode*/ | (0x1 << 12) /*funct3*/ | (csr << 20) | ((rs1 & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static uint32_t addi(uint32_t rd, uint32_t rs1, uint32_t imm)
    {
        /*
        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        imm   |  rs1  | funct3 |  rd  | opcode 
        
        funct3 = 000
        opcode = 001 0011
        */
        return 0x13 /*opcode*/ | (imm << 20) | ((rs1 & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static uint32_t lui(uint32_t rd, uint32_t imm)
    {
        /*
        31 12 | 11 7 | 6    0
        imm   |  rd  | opcode

        opcode = 011 0111
        */
        return 0x37 /*opcode*/ | (imm << 12) | ((rd & 0xf) << 7);
    }

    static uint32_t jalr(uint32_t rd, uint32_t rs1, uint32_t imm)
    {
        /*
        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        imm   |  rs1  | funct3 |  rd  | opcode 

        funct3 = 000
        opcode = 110 0111
        */

        return 0x67 /*opcode*/ | (imm << 20) | ((rs1 & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static uint32_t jal(uint32_t rd, uint32_t imm)
    {
        /*
        31      | 30     21 |   20    | 19      12 | 11 7 | 6    0
        imm[20] | imm[10:1] | imm[11] | imm[19:12] |  rd  | opcode

        opcode = 110 1111
        */
        return 0x6F /*opcode*/ | (imm >> 20 << 31) | ((imm & 0x7fe) << 20) | ((imm & (1 << 11)) << 9) | (imm & (0xff << 12)) | ((rd & 0xf) << 7);
    }

    static uint32_t csrrsi(uint32_t rd, uint32_t csr, uint32_t imm)
    {
        /*
        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        csr   |  imm  | funct3 |  rd  | opcode 

        funct3 = 110
        opcode = 111 0011
        */
        return 0x73 /*opcode*/ | (0x6 << 12) /*funct3*/ | (csr << 20) | ((imm & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static uint32_t csrrci(uint32_t rd, uint32_t csr, uint32_t imm)
    {
        /*
        31 20 | 19 15 | 14  12 | 11 7 | 6    0
        csr   |  imm  | funct3 |  rd  | opcode 

        funct3 = 111
        opcode = 111 0011
        */
        return 0x73 /*opcode*/ | (0x7 << 12) /*funct3*/ | (csr << 20) | ((imm & 0x1f) << 15) | ((rd & 0xf) << 7);
    }

    static constexpr uint32_t dret = 0x7b200073U;
};

#endif

