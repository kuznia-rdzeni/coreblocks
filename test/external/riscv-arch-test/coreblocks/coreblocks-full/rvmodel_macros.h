#ifndef _RVMODEL_MACROS_H
#define _RVMODEL_MACROS_H

#define STANDARD_SM_SUPPORTED

#define RVMODEL_DATA_SECTION

#define RVMODEL_ENDTEST_ADDRESS 0xF0000000
#define RVMODEL_CONSOLE_ADDRESS 0xF0001000
#define RVMODEL_ACCESS_FAULT_ADDRESS 0x00000000
#define RVMODEL_INTERRUPT_GENERATOR_ADDRESS 0xF0002000

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

##### Machine Timer / Software (via CLINT) #####

#define CLINT_BASE_ADDRESS        0xE1000000
#define RVMODEL_MTIME_ADDRESS     (CLINT_BASE_ADDRESS + 0xBFF8)
#define RVMODEL_MTIMECMP_ADDRESS  (CLINT_BASE_ADDRESS + 0x4000)
#define RVMODEL_MSIP_ADDRESS      (CLINT_BASE_ADDRESS + 0x0)

##### Machine / Supervisor External Interrupts (via PLIC) #####

/* PLIC base and SiFive-compatible register offsets.
 * Context 0 = M-mode (MEI), Context 1 = S-mode (SEI).
 * Two dedicated PLIC sources are used so each context has an independent interrupt line:
 *   MEXT_INT_SRC (source 1) is registered only in M-mode context 0.
 *   SEXT_INT_SRC (source 2) is registered only in S-mode context 1.
 *
 * Writing (1<<31)|(1<<src) to RVMODEL_INTERRUPT_GENERATOR_ADDRESS asserts source src.
 * Writing        (1<<src)  to RVMODEL_INTERRUPT_GENERATOR_ADDRESS deasserts source src.
 */
#define PLIC_BASE_ADDRESS    0xE2000000
#define PLIC_ENABLE_ADDRESS  (PLIC_BASE_ADDRESS + 0x002000)   /* M-mode context 0 enable bits */
#define PLIC_THRESH_ADDRESS  (PLIC_BASE_ADDRESS + 0x200000)   /* M-mode context 0 priority threshold */
#define PLIC_CLAIM_ADDRESS   (PLIC_BASE_ADDRESS + 0x200004)   /* M-mode context 0 claim/complete */
#define PLIC_SENABLE_ADDRESS (PLIC_BASE_ADDRESS + 0x002080)   /* S-mode context 1 enable bits */
#define PLIC_STHRESH_ADDRESS (PLIC_BASE_ADDRESS + 0x201000)   /* S-mode context 1 priority threshold */
#define PLIC_SCLAIM_ADDRESS  (PLIC_BASE_ADDRESS + 0x201004)   /* S-mode context 1 claim/complete */
#define MEXT_INT_SRC 1   /* PLIC source ID dedicated to M-mode external interrupts */
#define SEXT_INT_SRC 2   /* PLIC source ID dedicated to S-mode external interrupts */

#define RVMODEL_SET_MEXT_INT(_R1, _R2)                                     \
  li _R1, 7;                                                                \
  li _R2, PLIC_BASE_ADDRESS;                                                \
  sw _R1, (4*MEXT_INT_SRC)(_R2);                                            \
  li _R1, (1 << MEXT_INT_SRC);                                              \
  li _R2, PLIC_ENABLE_ADDRESS;                                              \
  sw _R1, 0(_R2);                                                           \
  li _R2, PLIC_THRESH_ADDRESS;                                              \
  sw zero, 0(_R2);                                                          \
  li _R1, (1 << 31) | (1 << MEXT_INT_SRC);                                  \
  li _R2, RVMODEL_INTERRUPT_GENERATOR_ADDRESS;                              \
  sw _R1, 0(_R2);

#define RVMODEL_CLR_MEXT_INT(_R1, _R2)                                     \
  li _R1, (1 << MEXT_INT_SRC);                                              \
  li _R2, RVMODEL_INTERRUPT_GENERATOR_ADDRESS;                              \
  sw _R1, 0(_R2);                                                           \
  li _R2, PLIC_CLAIM_ADDRESS;                                               \
  lw _R1, 0(_R2);                                                           \
  sw _R1, 0(_R2);

#define RVMODEL_SET_SEXT_INT(_R1, _R2)                                     \
  li _R1, 7;                                                                \
  li _R2, PLIC_BASE_ADDRESS;                                                \
  sw _R1, (4*SEXT_INT_SRC)(_R2);                                            \
  li _R1, (1 << SEXT_INT_SRC);                                              \
  li _R2, PLIC_SENABLE_ADDRESS;                                             \
  sw _R1, 0(_R2);                                                           \
  li _R2, PLIC_STHRESH_ADDRESS;                                             \
  sw zero, 0(_R2);                                                          \
  li _R1, (1 << 31) | (1 << SEXT_INT_SRC);                                  \
  li _R2, RVMODEL_INTERRUPT_GENERATOR_ADDRESS;                              \
  sw _R1, 0(_R2);

#define RVMODEL_CLR_SEXT_INT(_R1, _R2)                                     \
  li _R1, (1 << SEXT_INT_SRC);                                              \
  li _R2, RVMODEL_INTERRUPT_GENERATOR_ADDRESS;                              \
  sw _R1, 0(_R2);                                                           \
  li _R2, PLIC_SCLAIM_ADDRESS;                                              \
  lw _R1, 0(_R2);                                                           \
  sw _R1, 0(_R2);

#define RVMODEL_SET_MSW_INT(_R1, _R2)             \
  li _R1, 1                                      ;\
  li _R2, RVMODEL_MSIP_ADDRESS                   ;\
  sw _R1, 0(_R2)

#define RVMODEL_CLR_MSW_INT(_R1, _R2)             \
  li _R2, RVMODEL_MSIP_ADDRESS                   ;\
  sw zero, 0(_R2)

#define RVMODEL_SET_SSW_INT(_R1, _R2)
#define RVMODEL_CLR_SSW_INT(_R1, _R2)

#endif // _RVMODEL_MACROS_H
