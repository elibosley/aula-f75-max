#include "f75_lighting.h"
static unsigned div255(unsigned value){return (value+1u+(value>>8))>>8;}
static unsigned blend(unsigned a,unsigned b,unsigned weight){return (a*(256u-weight)+b*weight)>>8;}
static unsigned wave(unsigned phase){phase&=255u;unsigned value=phase<128u?phase*2u:(255u-phase)*2u;return div255(value*value);}
static unsigned distance(unsigned a,unsigned b,unsigned circumference){unsigned value=a>b?a-b:b-a;return value>circumference/2u?circumference-value:value;}
static void palette(unsigned phase,unsigned color[3]){
    static const uint8_t colors[6][3]={{140,218,202},{86,204,238},{200,170,246},{240,162,194},{244,176,124},{176,208,136}};
    if(phase>=1536u)phase-=1536u;
    unsigned index=phase>>8,next=index==5?0:index+1,weight=phase&255u;
    for(unsigned channel=0;channel<3;++channel)color[channel]=blend(colors[index][channel],colors[next][channel],weight);
}
void f75_lighting_frame(const f75_config *config,uint8_t brightness,uint32_t now,uint8_t output[F75_LIGHT_BYTES]){
    if(!config||!output)return;
    if(brightness>100)brightness=100;
    unsigned speed=config->speed>100?100:config->speed;
    unsigned period=24000u-speed*180u;
    unsigned phase=config->reduced_motion?0:((now%period)*256u/period);
    unsigned peak=brightness*127u/100u;
    for(unsigned row=0;row<6;++row)for(unsigned col=0;col<15;++col){
        unsigned color[3];
        switch(config->effect){
        case 1: /* Tidal: a pastel color wave across the columns. */
            palette(phase*6u+col*64u+row*16u,color);
            for(unsigned ch=0;ch<3;++ch)color[ch]=blend(color[ch],config->color[ch],64);
            break;
        case 2: { /* Rain: staggered cyan drops descend over an indigo bed. */
            static const uint8_t bed[3]={24,20,68},drop[3]={84,220,246};
            unsigned position=((phase+col*37u)&255u)*6u;
            unsigned delta=distance(row*256u,position,1536u);
            unsigned weight=delta<512u?(512u-delta)>>1:0;
            for(unsigned ch=0;ch<3;++ch)color[ch]=blend(bed[ch],blend(drop[ch],config->color[ch],64),weight);
            break;
        }
        case 3: { /* Trails: one amber ribbon moves across a purple background. */
            static const uint8_t bed[3]={40,28,100},ribbon[3]={248,186,104};
            unsigned position=phase*15u+row*40u;
            if(position>=3840u)position-=3840u;
            unsigned delta=distance(col*256u,position,3840u);
            unsigned weight=delta<1024u?(1024u-delta)>>2:0;
            for(unsigned ch=0;ch<3;++ch)color[ch]=blend(bed[ch],blend(ribbon[ch],config->color[ch],32),weight);
            break;
        }
        case 4: { /* Constellation: fixed star positions, long fades, no random cuts. */
            static const uint8_t bed[3]={16,24,56},star[3]={232,214,248};
            unsigned seed=row*59u+col*101u;
            unsigned weight=(seed&7u)<2u?wave(phase+seed):0;
            for(unsigned ch=0;ch<3;++ch)color[ch]=blend(bed[ch],blend(star[ch],config->color[ch],48),weight);
            break;
        }
        default:
            for(unsigned ch=0;ch<3;++ch)color[ch]=config->color[ch];
            break;
        }
        for(unsigned ch=0;ch<3;++ch)output[ch*90u+row*15u+col]=(uint8_t)div255(color[ch]*peak);
    }
}
