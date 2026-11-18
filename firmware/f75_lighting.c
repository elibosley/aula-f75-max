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
static void spectrum(unsigned phase,unsigned color[3]){
    static const uint8_t colors[6][3]={{255,0,0},{255,255,0},{0,255,0},{0,255,255},{0,0,255},{255,0,255}};
    phase%=1536u;unsigned index=phase>>8,next=index==5?0:index+1;
    for(unsigned ch=0;ch<3;++ch)color[ch]=blend(colors[index][ch],colors[next][ch],phase&255u);
}
static unsigned absolute(int value){return (unsigned)(value<0?-value:value);}
/* Integer octants avoid floating point and lookup buffers on the Cortex-M0. */
static unsigned angle(int x,int y){
    unsigned ax=absolute(x),ay=absolute(y);
    unsigned a=ax>=ay?(ax?ay*192u/ax:0):384u-ax*192u/ay;
    if(x<0)a=768u-a;
    if(y<0)a=1536u-a;
    return a%1536u;
}
static void tint(unsigned color[3],const uint8_t a[3],const uint8_t b[3],unsigned weight){
    for(unsigned ch=0;ch<3;++ch)color[ch]=blend(a[ch],b[ch],weight);
}
static void level(unsigned color[3],unsigned weight){
    for(unsigned ch=0;ch<3;++ch)color[ch]=div255(color[ch]*weight);
}
void f75_lighting_frame(const f75_config *config,uint8_t brightness,uint32_t now,uint8_t output[F75_LIGHT_BYTES]){
    if(!config||!output)return;
    if(brightness>100)brightness=100;
    unsigned speed=config->speed>100?100:config->speed;
    /* Frequency follows the slider: 50% is the former 100% (six seconds),
     * 100% takes three seconds, and 0% freezes the pattern. */
    unsigned period=speed?300000u/speed:300000u;
    unsigned phase=config->reduced_motion||!speed?0:((now%period)*256u/period);
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
        case 5: /* Rainbow wave. */
            spectrum(phase*6u+col*96u,color);break;
        case 6: /* Uniform rainbow cycle. */
            spectrum(phase*6u,color);break;
        case 7: { /* Expanding rainbow rings, stretched to the physical key grid. */
            unsigned radius=absolute((int)col*2-14)+absolute((int)row*5-12);
            spectrum(phase*6u+radius*64u,color);break;
        }
        case 8: { /* Spiral: angle plus distance from the center. */
            int x=(int)col*2-14,y=(int)row*5-12;
            spectrum(phase*6u+angle(x,y)+(absolute(x)+absolute(y))*48u,color);break;
        }
        case 9:
            spectrum(col*96u+row*48u,color);level(color,32u+wave(phase)*223u/255u);break;
        case 10:
            spectrum(phase*6u+col*96u+row*32u,color);
            for(unsigned ch=0;ch<3;++ch)color[ch]=blend(color[ch],255u,128u);
            break;
        case 11: {
            static const uint8_t a[3]={10,220,120},b[3]={126,36,232};
            tint(color,a,b,wave(phase+col*11u+row*19u));
            level(color,100u+wave(phase+col*23u)*155u/255u);break;
        }
        case 12: {
            static const uint8_t a[3]={255,112,52},b[3]={142,48,188};
            tint(color,a,b,wave(phase+col*10u+row*12u));break;
        }
        case 13: {
            static const uint8_t a[3]={0,32,184},b[3]={0,232,200};
            tint(color,a,b,wave(phase+col*15u+row*24u));break;
        }
        case 14: {
            static const uint8_t a[3]={164,8,0},b[3]={255,200,12};
            unsigned heat=(wave(phase+col*29u+row*21u)+wave(phase+col*13u+row*37u))/2u;
            tint(color,a,b,heat);break;
        }
        case 15: {
            static const uint8_t a[3]={255,72,168},b[3]={88,224,255};
            tint(color,a,b,wave(phase+col*18u+row*9u));break;
        }
        case 16: { /* Smooth falling green streams, never a random frame cut. */
            unsigned glow=wave(phase+col*37u+row*32u);
            color[0]=glow/12u;color[1]=12u+glow*243u/255u;color[2]=glow/6u;break;
        }
        case 17: {
            unsigned seed=row*59u+col*101u;
            spectrum(seed*7u,color);level(color,12u+wave(phase+seed)*243u/255u);break;
        }
        case 18: {
            unsigned weight=wave(phase);
            if((row+col)&1u)weight=255u-weight;
            spectrum((row+col)*128u,color);level(color,20u+weight*235u/255u);break;
        }
        case 19:
            spectrum(col*96u+row*64u,color);level(color,16u+wave(phase+col*64u+row*64u)*239u/255u);break;
        case 20: {
            unsigned head=(phase*15u+row*64u)%3840u;
            unsigned tail=(head+3840u-col*256u)%3840u;
            unsigned glow=tail<2816u?(2816u-tail)*243u/2816u:(tail-2816u)*243u/1024u;
            spectrum(col*80u+row*48u,color);level(color,12u+glow);break;
        }
        case 21:
            spectrum(phase*6u+angle((int)col*2-14,(int)row*5-12)*3u,color);break;
        case 22:
            for(unsigned ch=0;ch<3;++ch)color[ch]=config->color[ch];
            level(color,20u+wave(phase)*235u/255u);break;
        case 23: /* A still spectrum; speed intentionally has no effect. */
            spectrum(col*96u+row*48u,color);break;
        case 24: {
            unsigned triangle=phase<128u?phase*2u:(255u-phase)*2u;
            unsigned delta=absolute((int)(triangle*14u)-(int)(col*256u));
            unsigned glow=delta<768u?(768u-delta)*239u/768u:0;
            for(unsigned ch=0;ch<3;++ch)color[ch]=config->color[ch];
            level(color,16u+glow);break;
        }
        default:
            for(unsigned ch=0;ch<3;++ch)color[ch]=config->color[ch];
            break;
        }
        for(unsigned ch=0;ch<3;++ch)output[ch*90u+row*15u+col]=(uint8_t)div255(color[ch]*peak);
    }
}
