/* SPDX-License-Identifier: GPL-2.0-or-later
 * Stock EP0 IN callback wrapper. Unknown reports and the vendor boot command
 * tail-call the original callback. No flash, option, clock or GPIO writes.
 */
.syntax unified
.cpu cortex-m0
.thumb
.section .text,"ax",%progbits
.balign 4
.global stock_rom_hook
.type stock_rom_hook,%function
.thumb_func
stock_rom_hook:
    push {r3,r4,r5,r6,r7,lr}
    ldr r4, =0x20001308
    ldrb r0, [r4, #0x12]
    cmp r0, #2
    bne original
    ldr r0, [r4, #0x14]
    ldr r1, =0x52353746 /* F75R */
    cmp r0, r1
    beq read_rom
    ldr r1, =0x53353746 /* F75S */
    cmp r0, r1
    beq read_registers
    ldr r1, =0x46353746 /* F75F: fixed diagnostic record, not arbitrary RAM */
    cmp r0, r1
    bne original
    ldr r7, =0x20007e00
    mov r5, r4
    adds r5, #0x24
    movs r6, #12
record_copy:
    ldr r0, [r7]
    str r0, [r5]
    adds r7, #4
    adds r5, #4
    subs r6, #1
    bne record_copy
    movs r0, #48
    str r0, [r4, #0x20]
    ldr r0, =0x47353746 /* F75G */
    b handled
read_registers:
    /* Read a fixed register list. No caller-selected peripheral addresses. */
    ldr r7, =registers
    mov r5, r4
    adds r5, #0x24
    movs r6, #12
snapshot:
    ldr r0, [r7]
    adds r7, #4
    ldr r0, [r0]
    str r0, [r5]
    adds r5, #4
    subs r6, #1
    bne snapshot
    movs r0, #48
    str r0, [r4, #0x20]
    ldr r0, =0x54353746 /* F75T */
    b handled
read_rom:
    ldr r5, [r4, #0x1c] /* offset */
    ldr r6, [r4, #0x20] /* length */
    cmp r6, #0
    beq original
    cmp r6, #48
    bhi original
    ldr r0, =4096
    cmp r5, r0
    bhi original
    subs r0, r0, r5
    cmp r6, r0
    bhi original
    ldr r7, =0x1fff0000
    adds r7, r7, r5
    mov r5, r4
    adds r5, #0x24
    movs r0, #0
    movs r1, #48
    mov r2, r5
zero_tail:
    strb r0, [r2]
    adds r2, #1
    subs r1, #1
    bne zero_tail
copy:
    ldrb r0, [r7]
    strb r0, [r5]
    adds r7, #1
    adds r5, #1
    subs r6, #1
    bne copy
    ldr r0, =0x44353746 /* F75D */
handled:
    str r0, [r4, #0x14]
    /* Consume this private request. Stock state 4 queues its unrelated
       settings parser, which otherwise rewrites response byte 3 to FF. */
    movs r0, #0
    strb r0, [r4, #0x12]
original:
    pop {r3,r4,r5,r6,r7}
    pop {r0}
    mov lr, r0
    ldr r0, =0x18ab
    bx r0
.balign 4
registers:
    .word 0x40060004,0x40060008,0x4006000c,0x40060010
    .word 0x40060024,0x4005e000,0x40046000,0x40046004
    .word 0x40046030,0xe000e100,0xe000e010,0x4005c010
.ltorg
.size stock_rom_hook, .-stock_rom_hook
