#include "f75_sprite.h"
typedef struct { const uint8_t *data;size_t bytes,bit; } bits;
static bool take(bits *s,unsigned count,unsigned *value){
    if(s->bit>s->bytes*8||count>s->bytes*8-s->bit)return false;
    unsigned result=0;
    for(unsigned i=0;i<count;i++,s->bit++)result|=((s->data[s->bit/8]>>(s->bit%8))&1u)<<i;
    *value=result;return true;
}
uint8_t f75_sprite_index(const uint8_t *packed,size_t pixel){
    size_t bit=pixel*6,byte=bit/8;unsigned shift=bit%8;
    unsigned value=packed[byte]>>shift;
    if(shift>2)value|=(unsigned)packed[byte+1]<<(8-shift);
    return (uint8_t)(value&63u);
}
static void store(uint8_t *packed,size_t pixel,unsigned value){
    size_t bit=pixel*6,byte=bit/8;unsigned shift=bit%8;
    packed[byte]|=(uint8_t)(value<<shift);
    if(shift>2)packed[byte+1]|=(uint8_t)(value>>(8-shift));
}
bool f75_sprite_decode(const uint8_t *source,size_t bytes,uint8_t *out,size_t capacity,size_t pixels){
    if(!source||!out||!bytes||bytes>6400||!pixels||pixels>6400)return false;
    size_t needed=(pixels*6+7)/8;if(capacity<needed)return false;
    for(size_t i=0;i<needed;i++)out[i]=0;
    bits input={source,bytes,0};size_t position=0;
    while(position<pixels){
        unsigned literal,value,length;
        if(!take(&input,1,&literal))return false;
        if(literal){if(!take(&input,6,&value))return false;store(out,position++,value);}
        else {
            if(!take(&input,11,&value)||!take(&input,5,&length))return false;
            size_t distance=value+1;length+=3;
            if(distance>position||length>pixels-position)return false;
            for(unsigned i=0;i<length;i++,position++)store(out,position,f75_sprite_index(out,position-distance));
        }
    }
    if(input.bytes*8-input.bit>=8)return false;
    unsigned padding;
    return take(&input,(unsigned)(input.bytes*8-input.bit),&padding)&&padding==0;
}
