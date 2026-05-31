#ifndef _RVMODEL_MACROS_H
#define _RVMODEL_MACROS_H

#define STANDARD_SM_SUPPORTED

#define RVMODEL_DATA_SECTION

#define RVMODEL_ENDTEST_ADDRESS 0xF0000000
#define RVMODEL_CONSOLE_ADDRESS 0xF0001000
#define RVMODEL_ACCESS_FAULT_ADDRESS 0x00000000

#define RVMODEL_HALT_PASS  \
  li x1, 1                ;\
  li t0, RVMODEL_ENDTEST_ADDRESS ;\
  sw x1, 0(t0)

#define RVMODEL_HALT_FAIL \
  li x1, 3                ;\
  li t0, RVMODEL_ENDTEST_ADDRESS ;\
  sw x1, 0(t0)

#define RVMODEL_IO_WRITE_STR(_R1, _R2, _R3, _STR_PTR) \
  li _R2, RVMODEL_CONSOLE_ADDRESS ;\
  mv _R3, _STR_PTR ;\
  beqz _R3, 2f     ;\
1:                 ;\
  lbu _R1, 0(_R3)  ;\
  beqz _R1, 2f     ;\
  sb _R1, 0(_R2)   ;\
  addi _R3, _R3, 1 ;\
  j 1b             ;\
2:

#define RVMODEL_INTERRUPT_LATENCY 100
#define RVMODEL_TIMER_INT_SOON_DELAY 100

#define CLINT_BASE_ADDRESS 0xE1000000
#define RVMODEL_MTIME_ADDRESS     (CLINT_BASE_ADDRESS + 0xBFF8)
#define RVMODEL_MTIMECMP_ADDRESS  (CLINT_BASE_ADDRESS + 0x4000)
#define RVMODEL_MSIP_ADDRESS      (CLINT_BASE_ADDRESS + 0x0)

#define RVMODEL_SET_MEXT_INT(_R1, _R2)
#define RVMODEL_CLR_MEXT_INT(_R1, _R2)

#define RVMODEL_SET_MSW_INT(_R1, _R2) \
  li _R1, 1; \
  li _R2, RVMODEL_MSIP_ADDRESS; \
  sw _R1, 0(_R2);

#define RVMODEL_CLR_MSW_INT(_R1, _R2) \
  li _R2, RVMODEL_MSIP_ADDRESS; \
  sw zero, 0(_R2);

#define RVMODEL_SET_SEXT_INT(_R1, _R2)
#define RVMODEL_CLR_SEXT_INT(_R1, _R2)
#define RVMODEL_SET_SSW_INT(_R1, _R2)
#define RVMODEL_CLR_SSW_INT(_R1, _R2)

#endif // _RVMODEL_MACROS_H
