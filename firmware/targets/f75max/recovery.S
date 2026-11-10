/* SPDX-License-Identifier: GPL-2.0-or-later
 * This path precedes the C runtime, clocks, scheduler, USB, and display.
 * Preserve it in every diagnostic image. It requires no RAM globals or HAL.
 */
.syntax unified
.cpu cortex-m0
.thumb
#include "wheel.h"
.global f75_wheel_matrix_row
.equ f75_wheel_matrix_row, F75_WHEEL_ROW
.global f75_wheel_matrix_col
.equ f75_wheel_matrix_col, F75_WHEEL_COL
.section .text.f75_recovery,"ax",%progbits
.balign 4
.global Reset_Handler
.global f75_recovery_begin
.global f75_recovery_end
.global f75_enter_rom
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
f75_recovery_begin:
    cpsid i
    ldr r0, =0x20007ffc
    ldr r1, [r0]
    ldr r2, =0xdeadbeef
    cmp r1, r2
    beq f75_enter_rom
    /* An explicit ROM return-to-application command must be able to leave
       recovery even if the button is still held. Consume this once; a cold
       boot still samples the physical button before any C initialization. */
    ldr r0, =0x20007ff8
    ldr r1, [r0]
    ldr r2, =0x52543546
    cmp r1, r2
    bne check_wheel
    movs r1, #0
    str r1, [r0]
    b normal_start
check_wheel:
    /* The physical wheel is C9 -> B14, matrix row 14 / column 0.
       Isolate that row before any C initialization. All other drive rows
       are low, so an ordinary key in the same sense column cannot enter ISP.
       No stack, initialized RAM, timer, PLL or HAL is required. */
    ldr r0, =0x40044000
    movs r2, #0xf0
    str r2, [r0, #0x28]
    ldr r1, [r0, #4]
    orrs r1, r2
    str r1, [r0, #4]
    ldr r0, =F75_WHEEL_DRIVE_PORT
    ldr r2, =0x43ff
    str r2, [r0, #0x28]
    ldr r1, [r0, #4]
    orrs r1, r2
    str r1, [r0, #4]
    ldr r0, =F75_WHEEL_SENSE_PORT
    ldr r2, =F75_WHEEL_SENSE_MASK
    ldr r1, [r0, #4]
    bics r1, r2
    str r1, [r0, #4]
    ldr r1, [r0, #8]
    ldr r3, =0x30000000
    bics r1, r3
    ldr r3, =0x20000000
    orrs r1, r3
    str r1, [r0, #8]
    ldr r1, =F75_WHEEL_DRIVE_PORT
    ldr r3, =F75_WHEEL_DRIVE_MASK
    str r3, [r1, #0x24]
    /* Bounded settling time, independent of the system timer. */
    ldr r3, =48000
1:  subs r3, #1
    bne 1b
    ldr r0, [r0]
    ands r0, r2
    ldr r3, =F75_WHEEL_DRIVE_MASK
    str r3, [r1, #0x28]
    cmp r0, #0
    bne f75_enter_rom
normal_start:
    ldr r0, =_crt0_entry
    movs r1, #1
    orrs r0, r1
    bx r0
.size Reset_Handler, .-Reset_Handler

.balign 4
.type f75_enter_rom,%function
.thumb_func
f75_enter_rom:
    cpsid i
    ldr r0, =0x20007ff8
    ldr r1, =0x52543546
    str r1, [r0]
    movs r0, #0
    msr CONTROL, r0
    isb
    /* The captured factory ROM's scatter table initializes 0x000..0x347
       to zero and places its stack immediately above that range. Entry 0301
       bypasses that C runtime, so provide the same RAM state explicitly. */
    ldr r1, =0x20000348
    msr MSP, r1
    ldr r1, =0x20007ffc
    str r0, [r1]
    ldr r1, =0xe000e010
    str r0, [r1]
    ldr r1, =0xe000e180
    mvns r0, r0
    str r0, [r1]
    ldr r1, =0xe000e280
    str r0, [r1]
    ldr r0, =0x20000000
    ldr r1, =0x20000348
    movs r2, #0
2:  str r2, [r0]
    adds r0, #4
    cmp r0, r1
    blo 2b
    /* Keep the flash mapping intact until executing in high-address ROM.
       Stock's direct entry never performs a keyed IVTM remap from flash. */
    dsb
    isb
    ldr r0, =0x1fff0301
    /* Match stock's PRIMASK state. The captured loader polls USB with its
       controller interrupts disabled; IRQ masking was not its missing driver. */
    cpsie i
    bx r0
.size f75_enter_rom, .-f75_enter_rom
.balign 4
.global HardFault_Handler
.type HardFault_Handler,%function
.thumb_func
HardFault_Handler:
    /* Keep a bounded exception record outside the ROM's low-RAM workspace.
       ROM programming/stock startup do not use this high SRAM region. */
    mov r3, lr
    mrs r0, MSP
    movs r2, #4
    tst r3, r2
    beq 3f
    mrs r0, PSP
3:  ldr r1, =0x20007e00
    ldr r2, =0x46373546
    str r2, [r1]
    str r0, [r1, #4]
    str r3, [r1, #8]
    mrs r2, CONTROL
    str r2, [r1, #12]
    ldr r2, =0x20000000
    cmp r0, r2
    blo 5f
    ldr r2, =0x20007fe0
    cmp r0, r2
    bhi 5f
    adds r1, #16
    movs r2, #8
4:  ldr r3, [r0]
    str r3, [r1]
    adds r0, #4
    adds r1, #4
    subs r2, #1
    bne 4b
5:  b f75_enter_rom
.size HardFault_Handler, .-HardFault_Handler
.ltorg
f75_recovery_end:
