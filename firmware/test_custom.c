#include "f75_transfer.h"
#include "f75_clock.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static struct {uint16_t key;bool down;} events[256];static unsigned count;
static void emit(void *context,uint16_t key,bool down){(void)context;assert(count<256);events[count].key=key;events[count++].down=down;}
static void put32(uint8_t *p,uint32_t value){memcpy(p,&value,4);}
int main(void){
    f75_clock clock={0};char text[6];f75_clock_text(&clock,text);assert(!strcmp(text,"--:--"));
    assert(f75_clock_set(&clock,86399,UINT32_MAX-500));f75_clock_tick(&clock,499);f75_clock_text(&clock,text);assert(!strcmp(text,"00:00"));
    assert(!f75_clock_set(&clock,86400,0));f75_clock_tick(&clock,599);assert(clock.seconds==0);f75_clock_tick(&clock,1499);assert(clock.seconds==1);
    f75_config config,out;f75_defaults(&config);f75_custom custom,decoded;f75_custom_defaults(&custom);
    uint8_t themed[F75_CUSTOM_BYTES];custom.screen_custom=1;custom.screen_color[0]=255;
    f75_custom_encode(&custom,themed);assert(themed[4]==2&&f75_custom_decode(themed,&decoded)&&decoded.screen_custom&&decoded.screen_color[0]==255);
    themed[2512]=2;put32(themed+3068,f75_crc32(themed,3068));assert(!f75_custom_decode(themed,&decoded));f75_custom_defaults(&custom);
    assert(f75_custom_valid(&custom));custom.keys[0][6]=F75_BIND_MACRO;
    custom.macro_length[0]=4;
    custom.steps[0][0]=(f75_macro_step){F75_MACRO_PRIMARY,0};
    custom.steps[0][1]=(f75_macro_step){6,10};
    custom.steps[0][2]=(f75_macro_step){6|F75_MACRO_UP,20};
    custom.steps[0][3]=(f75_macro_step){F75_MACRO_PRIMARY|F75_MACRO_UP,0};
    assert(f75_custom_valid(&custom));
    uint8_t envelope[F75_ENVELOPE_BYTES];uint32_t generation;
    f75_envelope_encode(&config,&custom,UINT32_MAX,envelope);
    assert(f75_envelope_decode(envelope,&out,&decoded,&generation)&&generation==UINT32_MAX);
    assert(!memcmp(&config,&out,sizeof(config))&&!memcmp(&custom,&decoded,sizeof(custom)));
    for(unsigned i=0;i<F75_ENVELOPE_BYTES;++i){envelope[i]^=1;assert(!f75_envelope_decode(envelope,&out,&decoded,&generation));envelope[i]^=1;}
    custom.steps[0][3].usage=0;assert(!f75_custom_valid(&custom));custom.steps[0][3].usage=F75_MACRO_PRIMARY|F75_MACRO_UP;
    custom.steps[0][1].usage=0xe3;custom.steps[0][2].usage=0xe3|F75_MACRO_UP;assert(!f75_custom_valid(&custom));
    custom.steps[0][1].usage=6;custom.steps[0][2].usage=6|F75_MACRO_UP;
    custom.keys[0][71]=4;assert(!f75_custom_valid(&custom));custom.keys[0][71]=0;
    custom.keys[1][0]=4;assert(!f75_custom_valid(&custom));custom.keys[1][0]=0;
    f75_macro_player player={0};count=0;
    assert(f75_macro_start(&player,&custom,0,F75_MAC,100,emit,NULL));
    for(unsigned time=100;time<200;++time)f75_macro_tick(&player,&custom,time,2,emit,NULL);
    assert(count==4&&events[0].key==0xe3&&events[0].down&&!events[3].down&&!player.active);
    count=0;assert(f75_macro_start(&player,&custom,0,F75_WINDOWS,UINT32_MAX-2,emit,NULL));
    f75_macro_tick(&player,&custom,UINT32_MAX-2,2,emit,NULL);assert(count==1&&events[0].key==0xe0);
    f75_macro_cancel(&player,emit,NULL);assert(count==2&&!events[1].down);
    custom.macro_repeat[0]=1;count=0;f75_macro_start(&player,&custom,0,F75_MAC,0,emit,NULL);
    for(unsigned time=0;time<100;++time)f75_macro_tick(&player,&custom,time,2,emit,NULL);
    assert(player.active&&count>=8);f75_macro_release(&player);
    for(unsigned time=100;time<200;++time)f75_macro_tick(&player,&custom,time,2,emit,NULL);
    assert(!player.active&&count%4==0);
    uint8_t pwm[270];memset(pwm,7,270);custom.colored[0][7]=1;custom.colors[0][7][0]=255;
    f75_custom_lighting(&custom,0,100,pwm);unsigned led=(7%6)*15+7/6;
    assert(pwm[led]==127&&!pwm[90+led]&&!pwm[180+led]&&pwm[0]==7);
    custom.layer_mask=2;custom.layer_colors[1][1]=255;f75_custom_lighting(&custom,1,100,pwm);
    assert(!pwm[led]&&pwm[90+led]==127&&!pwm[180+led]);
    custom.colored[1][7]=1;custom.colors[1][7][2]=255;f75_custom_lighting(&custom,1,0,pwm);
    for(unsigned i=0;i<270;++i)assert(!pwm[i]);
    f75_transfer t={0};uint8_t q[32]={0},r[32],bundle[F75_BUNDLE_BYTES];
    f75_bundle_encode(&config,&custom,bundle);memcpy(q,"F75utest",8);put32(q+8,0x12345678);
    q[12]=1;q[13]=F75_BUNDLE_BYTES&255;q[14]=F75_BUNDLE_BYTES>>8;put32(q+15,f75_crc32(bundle,sizeof(bundle)));
    assert(f75_transfer_receive(&t,q,r,0,&config,&custom)&&!r[12]);
    q[12]=2;q[13]=17;q[14]=0;f75_transfer_receive(&t,q,r,1,&config,&custom);assert(r[12]==3&&!t.next);
    for(unsigned offset=0;offset<F75_BUNDLE_BYTES;offset+=17){
        q[13]=offset;q[14]=offset>>8;unsigned n=F75_BUNDLE_BYTES-offset;if(n>17)n=17;memcpy(q+15,bundle+offset,n);
        f75_transfer_receive(&t,q,r,2+offset,&config,&custom);assert(!r[12]);
    }
    q[12]=3;q[13]=F75_BUNDLE_BYTES&255;q[14]=F75_BUNDLE_BYTES>>8;q[15]=1;
    f75_transfer_receive(&t,q,r,5000,&config,&custom);assert(!r[12]&&t.phase==3&&t.save);
    assert(f75_bundle_decode(t.bytes,&out,&decoded));t.phase=5;
    q[12]=4;f75_transfer_receive(&t,q,r,5001,&config,&custom);assert(!r[12]&&t.phase==2);
    for(unsigned offset=0;offset<F75_BUNDLE_BYTES;offset+=17){
        q[12]=5;q[13]=offset;q[14]=offset>>8;f75_transfer_receive(&t,q,r,5002+offset,&config,&custom);
        unsigned n=F75_BUNDLE_BYTES-offset;if(n>17)n=17;assert(!r[12]&&!memcmp(r+15,bundle+offset,n));
    }
    q[12]=6;f75_transfer_receive(&t,q,r,9000,&config,&custom);assert(!r[12]&&!t.phase);
    q[12]=2;f75_transfer_receive(&t,q,r,9001,&config,&custom);assert(r[12]==4);
    q[12]=1;q[13]=F75_BUNDLE_BYTES&255;q[14]=F75_BUNDLE_BYTES>>8;put32(q+15,0);f75_transfer_receive(&t,q,r,9002,&config,&custom);assert(!r[12]);
    q[12]=6;put32(q+8,0x9999);f75_transfer_receive(&t,q,r,9003,&config,&custom);assert(r[12]==4&&t.phase==1);
    put32(q+8,0x12345678);q[12]=2;
    for(unsigned offset=0;offset<F75_BUNDLE_BYTES;offset+=17){q[13]=offset;q[14]=offset>>8;unsigned n=F75_BUNDLE_BYTES-offset;if(n>17)n=17;memcpy(q+15,bundle+offset,n);f75_transfer_receive(&t,q,r,9004,&config,&custom);assert(!r[12]);}
    q[12]=3;q[13]=F75_BUNDLE_BYTES&255;q[14]=F75_BUNDLE_BYTES>>8;q[15]=0;f75_transfer_receive(&t,q,r,9005,&config,&custom);assert(r[12]==2&&t.phase==6);
    q[12]=1;put32(q+15,0);f75_transfer_receive(&t,q,r,9006,&config,&custom);assert(!r[12]);q[12]=2;q[13]=q[14]=0;
    f75_transfer_receive(&t,q,r,30007,&config,&custom);assert(r[12]==4&&t.phase==0);
    puts("Custom settings: CRC corruption, protected keys, macro ownership/timing/cancel, layer colors and transactional upload/download passed.");
}
