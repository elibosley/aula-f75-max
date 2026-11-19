#include "f75_lighting.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void){
    f75_config c;f75_defaults(&c);uint8_t frames[F75_LIGHT_EFFECT_COUNT][270],previous[270],first[270],out[272];unsigned largest=0;
    /* Keep the original six-second smoothness bounds at their new 50% point. */
    c.speed=50;
    for(unsigned effect=0;effect<F75_LIGHT_EFFECT_COUNT;++effect){
        c.effect=effect;
        for(unsigned b=0;b<=100;b+=25){
            out[0]=0xa5;out[271]=0x5a;f75_lighting_frame(&c,b,1000,out+1);
            assert(out[0]==0xa5&&out[271]==0x5a);
            for(unsigned i=1;i<=270;++i){assert(out[i]<=127);if(!b)assert(!out[i]);}
        }
        for(unsigned now=0;now<=6000;now+=25){
            f75_lighting_frame(&c,100,now,out+1);
            if(!now)memcpy(first,out+1,270);
            else for(unsigned i=0;i<270;++i){unsigned a=out[i+1],b=previous[i],d=a>b?a-b:b-a;if(d>largest)largest=d;if(d>(effect<5?4u:8u))fprintf(stderr,"Effect %u at %u channel %u delta %u\n",effect,now,i,d);assert(d<=(effect<5?4u:8u));}
            for(unsigned key=0;key<90;++key)assert(out[1+key]+out[91+key]+out[181+key]>0);
            if(!effect||effect==23)assert(!memcmp(first,out+1,270));
            memcpy(previous,out+1,270);
        }
        assert(!memcmp(first,previous,270));
        f75_lighting_frame(&c,100,1000,frames[effect]);
        c.reduced_motion=1;f75_lighting_frame(&c,100,1000,first);f75_lighting_frame(&c,100,17000,previous);
        assert(!memcmp(first,previous,270));c.reduced_motion=0;
    }
    unsigned minimum=1000;
    for(unsigned a=0;a<F75_LIGHT_EFFECT_COUNT;++a)for(unsigned b=a+1;b<F75_LIGHT_EFFECT_COUNT;++b){
        unsigned total=0;for(unsigned i=0;i<270;++i)total+=frames[a][i]>frames[b][i]?frames[a][i]-frames[b][i]:frames[b][i]-frames[a][i];
        assert(total>270u*3u);if(total/270<minimum)minimum=total/270;
    }
    for(unsigned effect=0;effect<F75_LIGHT_EFFECT_COUNT;++effect){
        uint8_t record[F75_RECORD_BYTES];f75_config restored;uint32_t generation;
        c.effect=(uint8_t)effect;f75_record_encode(&c,7,record);
        assert(record[128]==F75_LIGHT_EFFECT_COUNT&&f75_record_decode(record,&restored,&generation));
        assert(restored.effect==effect&&generation==7);
        for(unsigned now=0;now<=3000;now+=25){
            c.speed=100;f75_lighting_frame(&c,100,now,first);
            c.speed=50;f75_lighting_frame(&c,100,now*2u,previous);
            assert(!memcmp(first,previous,270));
        }
        c.speed=0;f75_lighting_frame(&c,100,0,first);f75_lighting_frame(&c,100,123456u,previous);
        assert(!memcmp(first,previous,270));
    }
    c.effect=5;c.speed=50;f75_lighting_frame(&c,100,3000,first);
    assert(first[0]==0&&first[90]==127&&first[180]==127); /* Former 100% midpoint. */
    c.effect=F75_LIGHT_EFFECT_COUNT;assert(!f75_config_valid(&c));
    printf("Lighting checks passed: %u distinct patterns, max PWM delta %u/25ms, minimum pair distance %u.\n",F75_LIGHT_EFFECT_COUNT,largest,minimum);
}
