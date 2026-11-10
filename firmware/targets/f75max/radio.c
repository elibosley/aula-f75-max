// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include <string.h>
#include "radio.h"
/* Supplier application a7d45875: UART2 init 0x12ea0, TX dispatcher
 * 0x45e4, receive dispatcher 0x4934. B7 TX / B6 RX, 115385 baud @48MHz.
 * The radio retains its own bonds. This adapter never updates radio firmware.
 * Acknowledgments have no transaction ID. Serialize packets and discard old
 * queued key reports before a route change. Do not infer a bond from TX ACK. */
enum { COMMAND_NONE, COMMAND_SELECT, COMMAND_PAIR };
typedef struct {uint32_t generation;uint8_t bytes[10],length,kind;} packet;
static packet queue[16];
static uint8_t head,tail,offset,retries;
static bool waiting,seen,connected,ack_pending;
static uint32_t sent_at,tx_packets,rx_packets,errors,last_event;
static uint8_t selected,last_command;
static volatile uint8_t rx[128],rx_head,rx_tail;
static volatile uint32_t rx_errors;
static uint8_t input[3],input_length,ack_offset;
static bool route_started,report_fault;
static uint32_t command_generation;
static uint8_t selection_status;

static bool enqueue(uint8_t type,const uint8_t *data,uint8_t length) {
    uint8_t next=(head+1u)&15u;
    if(length>8||next==tail){++errors;return false;}
    packet *p=&queue[head];p->generation=0;p->kind=COMMAND_NONE;p->bytes[0]=type;
    uint8_t sum=type;
    for(unsigned i=0;i<length;++i){p->bytes[i+1]=data[i];sum+=data[i];}
    p->bytes[length+1]=sum;p->length=length+2;head=next;return true;
}
static bool command(uint8_t value,uint8_t kind){
    uint8_t index=head;
    if(!enqueue(0xa6,&value,1))return false;
    if(!++command_generation)++command_generation;
    queue[index].generation=command_generation;queue[index].kind=kind;
    last_command=value;
    if(kind==COMMAND_SELECT)selection_status=F75_RADIO_SELECT_PENDING;
    return true;
}
OSAL_IRQ_HANDLER(Vector60) {
    OSAL_IRQ_PROLOGUE();
    /* RX only: no display, allocation, settings, or host actions in the IRQ. */
    for(unsigned n=0;n<32;++n){
        uint32_t status=SN_UART2->LS;
        if(!(status&1u))break;
        uint8_t value=SN_UART2->RB,next=(rx_head+1u)&127u;
        if(status&0x9eu)++rx_errors;
        else if(next!=rx_tail){rx[rx_head]=value;rx_head=next;}
        else ++rx_errors;
    }
    OSAL_IRQ_EPILOGUE();
}
void f75_radio_init(void){
    SN_SYS1->AHBCLKEN|=1u<<18;
    /* Only UART2 mux fields. Preserve all PWM and panel assignments. */
    /* Stock 0x7e50 leaves both CFG fields at zero: digital input with
     * pull-up. The TX idle level also depends on this board configuration. */
    gpio_set_pin_input_high(B6);gpio_set_pin_input_high(B7);
    SN_PFPA->UART=(SN_PFPA->UART&~0xf00u)|0xf00u;
    NVIC_DisableIRQ(UART2_IRQn);
    SN_UART2->CTRL=0;SN_UART2->LC=0x83;SN_UART2->FD=0;
    SN_UART2->DLM=0;SN_UART2->DLL=26;SN_UART2->LC=3;
    SN_UART2->FIFOCTRL=7;SN_UART2->IE=1;SN_UART2->CTRL=0xc1;
    NVIC_ClearPendingIRQ(UART2_IRQn);NVIC_SetPriority(UART2_IRQn,2);NVIC_EnableIRQ(UART2_IRQn);
    command(0x11,COMMAND_SELECT);
}
static void receive_packet(void){
    uint8_t a=input[0],b=input[1];
    if(a==0x61){
        if(b!=0x0d||input[2]!=0x0a){++errors;return;}
        seen=true;++rx_packets;
        if(waiting){
            packet *p=&queue[tail];
            if(p->kind==COMMAND_SELECT&&p->generation==command_generation)selection_status=F75_RADIO_SELECT_ACKED;
            waiting=false;offset=0;tail=(tail+1u)&15u;retries=0;
        }
        return;
    }
    if((a!=0x5a&&a!=0x5b&&a!=0x5c)||(unsigned)a+b!=input[2]){++errors;return;}
    seen=true;++rx_packets;last_event=((uint32_t)a<<8)|b;
    if(a==0x5b&&b==0x43)return; // stock discards this acknowledgment
    ack_pending=true;
    /* Stock 0x4a3e treats the host LED-status packet as link evidence.
     * A connection event can precede its generic TX acknowledgment. */
    if(a==0x5a&&b<8&&route_started&&selected)connected=true;
    if(a==0x5b&&b==0x32&&route_started&&selected)connected=true;
    if(a==0x5b&&b==0x33)connected=false;
}
static bool transmit(const uint8_t *bytes,uint8_t length,uint8_t *position){
    uint16_t start=SN_CT16B4->TC;
    unsigned spins=0;
    while(*position<length){
        if(SN_UART2->LS&(1u<<5)){SN_UART2->TH=bytes[*position];++*position;}
        else if((uint16_t)((uint16_t)SN_CT16B4->TC-start)>=375u||++spins>=100000u)return false;
    }
    return true;
}
void f75_radio_task(uint32_t now){
    for(unsigned n=0;n<128&&rx_tail!=rx_head;++n){
        uint8_t value=rx[rx_tail];rx_tail=(rx_tail+1u)&127u;
        if(!input_length&&value!=0x61&&value!=0x5a&&value!=0x5b&&value!=0x5c)continue;
        input[input_length++]=value;
        if(input_length==3){receive_packet();input_length=0;}
    }
    /* The supplier retries twice, at 5ms intervals. A bounded retry cannot
     * wedge USB, rendering, or recovery when the radio is powered off. */
    if(waiting&&now-sent_at>=10u){
        waiting=false;offset=0;
        if(++retries>2){
            packet *p=&queue[tail];
            if(p->kind==COMMAND_SELECT&&p->generation==command_generation)selection_status=F75_RADIO_SELECT_FAILED;
            /* A report ACK timeout describes the UART transaction, not the
             * RF link. Keep the last link event until a disconnect, route
             * change, pairing request, or report-queue fault supersedes it.
             * Selection still fails through its independent status above. */
            ++errors;tail=(tail+1u)&15u;retries=0;
        }
    }
    if(!(SN_UART2->LS&(1u<<5)))return;
    if(ack_pending&&(!offset||waiting)){
        static const uint8_t ack[]={0x61,0x0d,0x0a};
        if(transmit(ack,3,&ack_offset)){ack_pending=false;ack_offset=0;}
        return;
    }
    if(waiting||head==tail)return;
    packet *p=&queue[tail];
    /* Match the supplier's THRE check for every byte. No assumption about
     * FIFO depth. Interrupts remain enabled; a whole packet takes <1ms at
     * the recovered baud rate. A stuck peripheral yields within 2ms. */
    if(transmit(p->bytes,p->length,&offset)){
        if(p->generation&&p->generation==command_generation)route_started=true;
        ++tx_packets;waiting=true;sent_at=now;
    }
}
bool f75_radio_select(uint8_t slot){
    if(slot>4)return false;
    /* Finish an already transmitted packet before the new transaction.
     * Discard queued reports, send an empty keyboard/consumer report, then
     * the selector command. This preserves release-before-switch ordering. */
    if(waiting){head=(tail+1u)&15u;}else{head=tail;offset=0;}
    selected=slot;connected=false;route_started=false;report_fault=false;
    uint8_t empty[8]={0};
    if(seen){enqueue(0xa1,empty,8);enqueue(0xa3,empty,2);enqueue(0xa8,empty,5);}
    bool queued=command(slot==0?0x11:slot==4?0x30:0x30+slot,COMMAND_SELECT);
    if(!queued)selection_status=F75_RADIO_SELECT_FAILED;
    return queued;
}
bool f75_radio_pair(void){
    if(selected<1||selected>3||!command(0x51,COMMAND_PAIR))return false;
    /* The old link can still deliver status while this command is queued.
     * Accept new link evidence only after the pairing bytes were sent. */
    connected=false;route_started=false;return true;
}
static void report_failed(void){
    /* Queue pressure must never lose only a key-up. Discard pending reports,
     * then release all keys. A new explicit selection clears this fault. */
    if(waiting)head=(tail+1u)&15u;else{head=tail;offset=0;}
    uint8_t empty[8]={0};enqueue(0xa1,empty,8);enqueue(0xa3,empty,2);enqueue(0xa8,empty,5);
    report_fault=true;connected=false;
    if(selection_status==F75_RADIO_SELECT_PENDING)selection_status=F75_RADIO_SELECT_FAILED;
}
void f75_radio_keyboard(const uint8_t report[8]){
    if(selected&&seen&&!report_fault&&!enqueue(0xa1,report,8))report_failed();
}
void f75_radio_consumer(uint16_t usage){
    uint8_t report[]={usage,usage>>8};
    if(selected&&seen&&!report_fault&&!enqueue(0xa3,report,2))report_failed();
}
void f75_radio_scroll(int8_t amount){
    f75_radio_mouse(0,amount);
}
void f75_radio_mouse(uint8_t buttons,int8_t amount){
    /* Supplier 0x4806 sends A8 + report bytes 1..5 + checksum. Its mouse
     * mapper at 0x28a8 writes vertical wheel at report offset 4. */
    uint8_t report[5]={buttons,0,0,(uint8_t)amount,0};
    if(selected&&seen&&!report_fault&&!enqueue(0xa8,report,5))report_failed();
}
bool f75_radio_seen(void){return seen;}
bool f75_radio_connected(void){return connected;}
bool f75_radio_busy(void){return head!=tail||waiting;}
uint8_t f75_radio_selection_status(void){return selection_status;}
void f75_radio_diagnostics(uint32_t out[6]){
    out[0]=(uint32_t)seen|((uint32_t)connected<<1)|((uint32_t)waiting<<2)|((uint32_t)report_fault<<3)|((uint32_t)selected<<8)|((uint32_t)last_command<<16);
    out[1]=tx_packets;out[2]=rx_packets;out[3]=errors+rx_errors;out[4]=last_event;out[5]=(SN_UART2->LS&255u)|((SN_PFPA->UART&65535u)<<8)|
        (((SN_GPIO1->DATA>>6)&3u)<<24)|(((SN_SYS1->AHBCLKEN>>18)&1u)<<26)|
        ((SN_UART2->CTRL&1u)<<27);
}
