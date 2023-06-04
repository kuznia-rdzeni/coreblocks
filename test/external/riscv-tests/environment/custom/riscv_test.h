// See LICENSE for license details.

#ifndef _ENV_PHYSICAL_SINGLE_CORE_H
#define _ENV_PHYSICAL_SINGLE_CORE_H

#include "../encoding.h"

//-----------------------------------------------------------------------
// Begin Macro
//-----------------------------------------------------------------------

#define TESTNUM gp
#define DEBUG_REG 0x80000000

#define RVTEST_RV32U
#define RVTEST_RV64U RVTEST_RV32U

#define INIT_XREG                                                       \
  li x1, 0;                                                             \
  li x2, 0;                                                             \
  li x3, 0;                                                             \
  li x4, 0;                                                             \
  li x5, 0;                                                             \
  li x6, 0;                                                             \
  li x7, 0;                                                             \
  li x8, 0;                                                             \
  li x9, 0;                                                             \
  li x10, 0;                                                            \
  li x11, 0;                                                            \
  li x12, 0;                                                            \
  li x13, 0;                                                            \
  li x14, 0;                                                            \
  li x15, 0;                                                            \
  li x16, 0;                                                            \
  li x17, 0;                                                            \
  li x18, 0;                                                            \
  li x19, 0;                                                            \
  li x20, 0;                                                            \
  li x21, 0;                                                            \
  li x22, 0;                                                            \
  li x23, 0;                                                            \
  li x24, 0;                                                            \
  li x25, 0;                                                            \
  li x26, 0;                                                            \
  li x27, 0;                                                            \
  li x28, 0;                                                            \
  li x29, 0;                                                            \
  li x30, 0;                                                            \
  li x31, 0;

#define RVTEST_CODE_BEGIN                                               \
        .section .text.init;                                            \
        .align  6;                                                      \
        .globl _start;                                                  \
_start:                                                                 \
        INIT_XREG;                                                      \
        li TESTNUM, 0;                                                  \
1:

//-----------------------------------------------------------------------
// End Macro
//-----------------------------------------------------------------------

#define RVTEST_CODE_END                                                 \
        unimp

//-----------------------------------------------------------------------
// Pass/Fail Macro
//-----------------------------------------------------------------------

#define RVTEST_PASS                                                     \
.pass:                                  \
        li      a0,DEBUG_REG;           \
        li      a1,0x0;                 \
        sw      a1,0(a0);               \
        j .pass;

#define RVTEST_FAIL                                                     \
.fail:                                  \
        li      a0,DEBUG_REG;           \
        mv      a1,TESTNUM;             \
        sw      a1,0(a0);               \
        j .fail;

//-----------------------------------------------------------------------
// Data Section Macro
//-----------------------------------------------------------------------

#define RVTEST_DATA_BEGIN                                               \
        .align 4

#define RVTEST_DATA_END

#endif
