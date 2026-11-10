.syntax unified
.cpu cortex-m0
.thumb
.section .text
.global checkpoint
.thumb_func
checkpoint:
    cpsid i
    /* A durable SRAM marker distinguishes an executed checkpoint from an
       immediate button-triggered ROM entry or a trapped HardFault. */
    ldr r0, =0x20007e00
    ldr r1, =0x43373546
    str r1, [r0]
    ldr r1, =F75_CHECKPOINT_ADDRESS
    str r1, [r0, #4]
    /* Force the host to observe a period without ROM replies. No drivers,
       interrupts, RTOS, display, or flash writes are used by this stub. */
    ldr r0, =120000
1:  subs r0, #1
    bne 1b
    /* Direct return: does not depend on SRAM retention through system reset. */
    ldr r0, =F75_ROM_RETURN
    movs r1, #1
    orrs r0, r1
    bx r0
