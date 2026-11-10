/* SPDX-License-Identifier: GPL-2.0-or-later
 * F75 Max / SN32F290 wired execution model. Not a silicon or radio model.
 * Real Cortex-M0, NVIC and SysTick are provided by QEMU's ARMv7M container.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/boards.h"
#include "hw/arm/armv7m.h"
#include "hw/arm/boot.h"
#include "hw/qdev-properties.h"
#include "hw/qdev-clock.h"
#include "hw/irq.h"
#include "system/address-spaces.h"
#include "qemu/timer.h"
#include "exec/cpu-interrupt.h"

#define TYPE_F75_MACHINE MACHINE_TYPE_NAME("f75max")
OBJECT_DECLARE_SIMPLE_TYPE(F75State, F75_MACHINE)
struct F75State {
    MachineState parent;
    ARMv7MState arm;
    MemoryRegion flash, ram, mmio, trace, rom, uart_trace;
    uint8_t *uart_data, uart_rx[256];
    unsigned uart_count, uart_head, uart_tail;
    bool uart_stuck;
    uint32_t regs[0x80000 / 4];
    uint32_t keys[15], inputs[4], spi_count, unknown;
    uint32_t spi_violations, spi_frames8, spi_frames16;
    uint32_t scan_byte_overlaps;
    uint32_t flash_words[2],flash_word_count,flash_erases,flash_programs,flash_illegal,flash_fail_at;
    uint8_t pma[512], *trace_data;
    int64_t timer_epoch[6];
    QEMUTimer *spi_timer, *pause_timer, *sof_timer, *row_timer;
    bool spi_stuck, pll_stuck, spi_busy, spi_received;
};
static const uint32_t gpio[] = {0x44000, 0x46000, 0x48000, 0x4a000};
static const uint8_t drive_port[] = {0,0,2,2,2,2,0,0,2,2,2,2,2,2,2};
static const uint8_t drive_bit[] = {4,5,0,1,2,3,6,7,4,5,6,7,14,8,9};
static const uint8_t sense_port[] = {1,1,1,3,0,0};
static const uint8_t sense_bit[] = {14,15,19,19,19,18};
#define R(a) s->regs[(a) / 4]
static void uart_irq(F75State *s) {
    qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm),8),
        (R(0x54004)&1) && s->uart_head!=s->uart_tail && (R(0x54030)&0x41)==0x41);
}
static void usb_irq(F75State *s) {
    uint32_t pending = R(0x5c004), en = R(0x5c000);
    bool irq = ((pending & 0xe2000000) && (en & 0x90000000)) ||
        ((pending & 0x01fe0000) && (en & 0x20000000)) ||
        ((pending & 0x00003f00) && (en & 0x40)) ||
        ((pending & 0x04000000) && (en & 0x40000000));
    qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm), 1), irq);
}
static void spi_done(void *opaque) {
    F75State *s = opaque;
    s->spi_busy=false;
    if(s->spi_received)R(0x1c014)|=1;
    s->spi_received=true;
    R(0x1c014) |= 4;
    qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm), 6), !!(R(0x1c010) & 4));
}
static void pause_cpu(void *opaque) {
    F75State *s = opaque;
    cpu_interrupt(CPU(s->arm.cpu), CPU_INTERRUPT_DEBUG);
}
static void usb_sof(void *opaque) {
    F75State *s = opaque;
    if (R(0x5c010) & (1u << 29)) {
        R(0x5c060) = (R(0x5c060) + 1) & 2047;
        if (R(0x5c000) & (1u << 30)) { R(0x5c004) |= 1u << 26; usb_irq(s); }
    }
    timer_mod(s->sof_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + 1000000);
}
static uint32_t timer_value(F75State *s, unsigned n) {
    unsigned base=n*0x2000;
    if (!(R(base)&1)) return R(base+4)&65535;
    uint64_t ticks=(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)-s->timer_epoch[n])*48/
        (1000*((R(base+8)&65535)+1));
    uint64_t count=R(base+4)+ticks;
    if(n==1) {
        /* CT16B1 MCTRL has real action bits at 24..29, not a key byte. */
        for(unsigned channel=0;channel<10;++channel)if(R(base+0x14)&(2u<<(channel*3))) {
            unsigned match=R(base+0x20+channel*4)&65535;
            if(!match)count=0;else if(count>=match)count%=match;
        }
    }
    unsigned stop=n==1 ? ((R(base+0x18)&(1u<<8))?0x50:0) :
        ((R(base+0x14)&(1u<<23))?0x44:0);
    if(stop && count>=R(base+stop)) {R(base)&=~1u;R(base+4)=R(base+stop);return R(base+4);}
    return count&65535;
}
static void schedule_row(F75State *s) {
    timer_del(s->row_timer);
    if((R(0x6000)&1) && (R(0x6014)&1) && R(0x6020)) {
        uint64_t ns=(uint64_t)(R(0x6020)+1)*(R(0x6008)+1)*1000000000/48000000;
        timer_mod(s->row_timer,qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)+ns);
    }
}
static void row_done(void *opaque) {
    F75State *s=opaque;
    R(0x60a8)|=1;
    if(R(0x6014)&2) {R(0x6004)=0;s->timer_epoch[3]=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);}
    if(R(0x6014)&4) R(0x6000)&=~1u;
    qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm),19),!!(R(0x6014)&1));
    schedule_row(s);
}
static bool known(hwaddr a) {
    return (a < 0xc000 && (a % 0x2000) < 0xc0) || (a >= 0x10000 && a < 0x10020) ||
        (a >= 0x1c000 && a < 0x1c024) ||
        (a >= 0x32000 && a < 0x32044) || (a >= 0x34000 && a < 0x34020) ||
        (a >= 0x40000 && a < 0x40020) ||
        (a >= 0x42000 && a < 0x42040) ||
        (a >= 0x44000 && a < 0x44040) || (a >= 0x46000 && a < 0x46040) ||
        (a >= 0x48000 && a < 0x48040) || (a >= 0x4a000 && a < 0x4a040) ||
        (a >= 0x54000 && a < 0x54038) ||
        (a >= 0x5c000 && a < 0x5c300) ||
        (a >= 0x5e000 && a < 0x5e020) ||
        (a >= 0x60000 && a < 0x60040) ||
        (a >= 0x62000 && a < 0x62040) || a >= 0x7f000;
}
static uint64_t f75_read(void *opaque, hwaddr a, unsigned size) {
    F75State *s = opaque;
    if (!known(a)) { if (s->unknown++ < 20) fprintf(stderr, "UNMODELED read %08"HWADDR_PRIx"\n", a + 0x40000000); }
    if(a==0x7f040)return s->uart_count;
    if(a==0x54014)return (s->uart_stuck?0:0x60)|(s->uart_head!=s->uart_tail);
    if(a==0x54008)return s->uart_head!=s->uart_tail?4:1;
    if(a==0x54000&&!(R(0x5400c)&0x80)){
        uint8_t value=0;
        if(s->uart_head!=s->uart_tail){value=s->uart_rx[s->uart_tail];s->uart_tail=(s->uart_tail+1)&255;}
        uart_irq(s);return value;
    }
    if (a == 0x7f004) return s->spi_count;
    if (a == 0x7f008) return s->unknown;
    if (a == 0x7f00c) return qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / 1000;
    if (a == 0x7f034) return s->spi_violations;
    if (a == 0x7f038) return s->spi_frames8;
    if (a == 0x7f03c) return s->spi_frames16;
    if (a == 0x7f050) return s->scan_byte_overlaps;
    if (a == 0x7f058) return s->flash_erases;
    if (a == 0x7f05c) return s->flash_programs;
    if (a == 0x7f060) return s->flash_illegal;
    if(a<0xc000 && (a%0x2000)==4) return timer_value(s,a/0x2000);
    if (a == 0x60008) return R(a) | (s->pll_stuck ? 0x31 : 0x71); /* oscillator/PLL ready */
    if (a == 0x6000c) return (R(a) & ~0x70) | ((R(a) & 7) << 4);
    if (a == 0x1c00c) return 1|(s->spi_busy?16:0)|(s->spi_received?64:4);
    if (a == 0x1c01c) {s->spi_received=false;return R(a);}
    for (int p = 0; p < 4; p++) if (a == gpio[p]) {
        uint32_t mode = R(a + 4), value = (R(a) & mode) | (s->inputs[p] & ~mode);
        for (int c = 0; c < 6; c++) if (sense_port[c] == p) value &= ~(1u << sense_bit[c]);
        for (int row = 0; row < 15; row++) if (R(gpio[drive_port[row]]) & R(gpio[drive_port[row]]+4) & (1u << drive_bit[row]))
            for (int c = 0; c < 6; c++) if ((s->keys[row] & (1u << c)) && sense_port[c] == p) value |= 1u << sense_bit[c];
        return value;
    }
    if (a >= 0x5c100 && a < 0x5c300) { uint32_t v = 0; memcpy(&v, s->pma + a - 0x5c100, size); return v; }
    return (R(a & ~3) >> (8 * (a & 3))) & (size == 4 ? UINT32_MAX : ((1u << (size * 8)) - 1));
}
static void f75_write(void *opaque, hwaddr a, uint64_t v, unsigned size) {
    F75State *s = opaque;
    if (!known(a)) { if (s->unknown++ < 20) fprintf(stderr, "UNMODELED write %08"HWADDR_PRIx"\n", a + 0x40000000); }
    if(a==0x7f044){
        unsigned next=(s->uart_head+1)&255;
        if(next!=s->uart_tail){s->uart_rx[s->uart_head]=v;s->uart_head=next;}
        uart_irq(s);return;
    }
    if(a==0x7f048){s->uart_stuck=!!v;return;}
    if(a==0x54000&&!(R(0x5400c)&0x80)){
        if(s->uart_count<65536)s->uart_data[s->uart_count++]=v;
        return;
    }
    if (a == 0x7f000) { R(0x5c004) |= v; usb_irq(s); return; }
    if (a >= 0x7f100 && a < 0x7f13c) { s->keys[(a - 0x7f100) / 4] = v; return; }
    if (a >= 0x7f200 && a < 0x7f210) { s->inputs[(a - 0x7f200) / 4] = v; return; }
    if (a == 0x7f010) { R(0x60010) = v; return; } /* ROM handoff prescaler */
    if (a == 0x7f020) { timer_mod(s->pause_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + v * 1000000); return; }
    if (a == 0x7f024) { s->spi_stuck = !!v; return; }
    if (a == 0x7f028) { s->pll_stuck = !!v; return; }
    if (a == 0x7f030) { s->spi_count = 0; return; } /* host drains trace between tiles */
    if (a == 0x7f064) {s->flash_fail_at=v;return;}
    /* Supplier 0x12b88 clears ERR with a zero write; it is not W1C. */
    if (a == 0x62004) {R(a)=(R(a)&1u)|(v&4u);return;}
    if (a == 0x6200c) {
        if(s->flash_word_count<2)s->flash_words[s->flash_word_count++]=v;
        else R(0x62004)|=4u;
        return;
    }
    if(a==0x62008){
        if(!(v&0x40u)){R(a)=v;s->flash_word_count=0;return;}
        uint32_t address=R(0x62010);uint8_t *flash=memory_region_get_ram_ptr(&s->flash);
        /* Deliberately restricted application-data model. Attempts to touch
         * code, option bytes or the trailer fail visibly. */
        if(!((address>=0x38000u&&address<0x3a000u)||(address>=0x3f000u&&address<0x3f800u))||(address&7u)||(v&4u)){
            ++s->flash_illegal;R(0x62004)|=4u;return;
        }
        if((v&3u)==2u){
            memset(flash+(address&~1023u),0xff,1024);++s->flash_erases;
        }else if((v&3u)==1u&&s->flash_word_count==2){
            ++s->flash_programs;
            if((s->flash_fail_at&&s->flash_programs>=s->flash_fail_at)||
               ldl_le_p(flash+address)!=UINT32_MAX||ldl_le_p(flash+address+4)!=UINT32_MAX){R(0x62004)|=4u;return;}
            stl_le_p(flash+address,s->flash_words[0]);stl_le_p(flash+address+4,s->flash_words[1]);
        }else {R(0x62004)|=4u;return;}
        R(a)=0;s->flash_word_count=0;return;
    }
    if (a >= 0x5c100 && a < 0x5c300) { memcpy(s->pma + a - 0x5c100, &v, size); return; }
    for (int p = 0; p < 4; p++) {
        if(!(R(0x46000)&(1u<<8)) && (a==gpio[p]+0x24 || a==gpio[p]+0x28)) {
            uint32_t mask=p==0?0xf0u:p==2?0x43ffu:0;
            uint32_t changed=a==gpio[p]+0x24?(~R(gpio[p])&v):(R(gpio[p])&v);
            if(changed&mask)++s->scan_byte_overlaps;
        }
        if(s->spi_busy && (a==gpio[p]+0x24 || a==gpio[p]+0x28)) {
            uint32_t mask=p==1?(1u<<8):p==3?(1u<<14):0;
            uint32_t changed=a==gpio[p]+0x24?(~R(gpio[p])&v):(R(gpio[p])&v);
            if(changed&mask)++s->spi_violations;
        }
        if (a == gpio[p] + 0x24) { R(gpio[p]) |= v; return; }
        if (a == gpio[p] + 0x28) { R(gpio[p]) &= ~v; return; }
    }
    if (a == 0x5c008) { R(0x5c004) &= ~v; usb_irq(s); return; }
    if(a<0xc000 && (a%0x2000)<0xc0) {
        unsigned n=a/0x2000,base=n*0x2000,offset=a-base;
        if(offset==0) {
            uint32_t count=timer_value(s,n);
            R(base+4)=(v&2)?0:count;
            s->timer_epoch[n]=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);v&=~2u;
        }
        if(offset==4) s->timer_epoch[n]=qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        if(n==1) {
            if(offset==0x14)v&=0x3fffffffu;
            if(offset==0x18)v&=0x1ffu;
            if(offset>=0x20&&offset<=0x50)v&=0xffffu;
            if(offset==0x98)v&=0xffffffu;
            if(offset==0xa0||offset==0xa4)v&=0xfffu;
        } else if((v&0xff000000)==0x5a000000) v&=0x00ffffff;
        if(offset==0xac) {
            R(base+0xa8)&=~v;
            if(n==3) qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm),19),!!(R(base+0xa8)&1));
            return;
        }
        R(a)=v;
        if(n==3 && (offset==0||offset==8||offset==0x14||offset==0x20))schedule_row(s);
        return;
    }
    if (a == 0x1c000) {
        if(s->spi_busy && ((v&0xc0)||!(v&1)))++s->spi_violations;
        if(v&0xc0){s->spi_busy=false;s->spi_received=false;timer_del(s->spi_timer);}
        v &= ~0xc0; /* self-clearing FIFO reset */
    }
    if (a == 0x1c018) { R(0x1c014) &= ~v; qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm), 6), 0); }
    if (a == 0x1c01c && (R(0x1c000) & 1)) {
        /* Host-only one-shot scheduling adversary: make a row IRQ pending at
         * the first selected byte, without changing the firmware image. */
        if(R(0x7f054)) {
            R(0x7f054)=0;R(0x60a8)|=1;
            qemu_set_irq(qdev_get_gpio_in(DEVICE(&s->arm),19),1);
        }
        if(s->spi_busy)++s->spi_violations;
        s->spi_busy=true;
        unsigned bits = ((R(0x1c000) >> 8) & 15) + 1;
        if(bits==8)++s->spi_frames8;
        if(bits==16)++s->spi_frames16;
        if (!(R(0x46000) & (1u << 8))) {
            for (int shift = bits > 8 ? 8 : 0; shift >= 0 && s->spi_count < 2097152; shift -= 8) {
                s->trace_data[s->spi_count * 2] = v >> shift;
                s->trace_data[s->spi_count * 2 + 1] = !!(R(0x4a000) & (1u << 14));
                s->spi_count++;
            }
        }
        uint64_t ns = ((uint64_t)bits * (2 * (R(0x1c008) & 255) + 2) * 1000000000 + 47999999) / 48000000;
        if (!s->spi_stuck) timer_mod(s->spi_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + ns);
    }
    unsigned shift = 8 * (a & 3);
    uint32_t mask = size == 4 ? UINT32_MAX : ((1u << (size * 8)) - 1) << shift;
    R(a & ~3) = (R(a & ~3) & ~mask) | ((uint32_t)v << shift);
    if (a == 0x5c080 || a == 0x5c08c) {
        uint32_t delta = a == 0x5c080 ? 0 : 12;
        uint32_t addr = R(0x5c078 + delta) & 511;
        if (addr <= 508) {
            if (v & 1) memcpy(s->pma + addr, &R(0x5c07c + delta), 4);
            if (v & 2) memcpy(&R(0x5c07c + delta), s->pma + addr, 4);
        }
        R(a) = 0;
    }
    if (a == 0x5c000) usb_irq(s);
    if(a==0x54004||a==0x54030)uart_irq(s);
}
static const MemoryRegionOps f75_ops = {
    .read = f75_read, .write = f75_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {.min_access_size = 1, .max_access_size = 4},
};
static void f75_init(MachineState *machine) {
    F75State *s = F75_MACHINE(machine);
    MemoryRegion *mem = get_system_memory();
    Clock *clk = clock_new(OBJECT(machine), "sysclk");
    clock_set_hz(clk, 48000000);
    memory_region_init_rom(&s->flash, NULL, "f75.flash", 0x40000, &error_fatal);
    memory_region_add_subregion(mem, 0, &s->flash);
    memory_region_init_ram(&s->ram, NULL, "f75.ram", 0x8000, &error_fatal);
    memory_region_add_subregion(mem, 0x20000000, &s->ram);
    memset(memory_region_get_ram_ptr(&s->ram), 0xa5, 0x8000);
    memory_region_init_rom(&s->rom, NULL, "f75.rom-and-options", 0x3000, &error_fatal);
    memory_region_add_subregion(mem, 0x1fff0000, &s->rom);
    /* Deliberate BKPT boundary. No factory ROM dump or simulated enumeration. */
    uint8_t *rom = memory_region_get_ram_ptr(&s->rom); rom[0x300] = 0; rom[0x301] = 0xbe;
    memory_region_init_ram(&s->trace, NULL, "f75.spi-trace", 4194304, &error_fatal);
    memory_region_add_subregion(mem, 0x60000000, &s->trace);
    s->trace_data = memory_region_get_ram_ptr(&s->trace);
    /* UART byte trace only. Radio replies require explicit host injection;
     * this model never claims that pairing or an RF link succeeded. */
    memory_region_init_ram(&s->uart_trace,NULL,"f75.uart-trace",65536,&error_fatal);
    memory_region_add_subregion(mem,0x61000000,&s->uart_trace);
    s->uart_data=memory_region_get_ram_ptr(&s->uart_trace);
    memory_region_init_io(&s->mmio, OBJECT(machine), &f75_ops, s, "f75.peripherals", 0x80000);
    memory_region_add_subregion(mem, 0x40000000, &s->mmio);
    s->inputs[0] = (1u << 10) | (1u << 2) | (1u << 3); s->inputs[1] = (1u << 2) | (1u << 17);
    R(0x60004) = 0x8002; R(0x6000c) = 0x44;
    object_initialize_child(OBJECT(machine), "armv7m", &s->arm, TYPE_ARMV7M);
    qdev_prop_set_string(DEVICE(&s->arm), "cpu-type", ARM_CPU_TYPE_NAME("cortex-m0"));
    qdev_prop_set_uint32(DEVICE(&s->arm), "num-irq", 32);
    object_property_set_link(OBJECT(&s->arm), "memory", OBJECT(mem), &error_fatal);
    qdev_connect_clock_in(DEVICE(&s->arm), "cpuclk", clk);
    sysbus_realize(SYS_BUS_DEVICE(&s->arm), &error_fatal);
    s->row_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, row_done, s);
    s->spi_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, spi_done, s);
    s->pause_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, pause_cpu, s);
    s->sof_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, usb_sof, s);
    timer_mod(s->sof_timer, 1000000);
    armv7m_load_kernel(s->arm.cpu, machine->kernel_filename, 0, 0x40000);
}
static void f75_class_init(ObjectClass *oc, const void *data) {
    MachineClass *mc = MACHINE_CLASS(oc);
    mc->desc = "F75 Max SN32F290 wired model (Cortex-M0)";
    mc->init = f75_init; mc->max_cpus = 1;
}
static const TypeInfo f75_info = {
    .name = TYPE_F75_MACHINE, .parent = TYPE_MACHINE,
    .instance_size = sizeof(F75State), .class_init = f75_class_init,
};
static void f75_register(void) { type_register_static(&f75_info); }
type_init(f75_register);
