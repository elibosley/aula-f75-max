#include "f75_sprite.h"
static bool take(f75_sprite_decoder *s,unsigned count,unsigned *value){
    if(s->bit>s->bytes*8||count>s->bytes*8-s->bit)return false;
    if(!count){*value=0;return true;}
    /* Tokens use at most eleven bits. Read only their covered bytes instead
     * of walking every bit in the display task. The bound above also covers
     * the optional second and third byte at a truncated stream boundary. */
    unsigned shift=s->bit%8;size_t byte=s->bit/8;
    unsigned result=s->data[byte]>>shift;
    if(count>8-shift)result|=(unsigned)s->data[byte+1]<<(8-shift);
    if(count>16-shift)result|=(unsigned)s->data[byte+2]<<(16-shift);
    s->bit+=count;*value=result&((1u<<count)-1u);return true;
}
static inline uint8_t index_at(const uint8_t *packed,size_t pixel){
    size_t bit=pixel*6,byte=bit/8;unsigned shift=bit%8;
    unsigned value=packed[byte]>>shift;
    if(shift>2)value|=(unsigned)packed[byte+1]<<(8-shift);
    return (uint8_t)(value&63u);
}
uint8_t f75_sprite_index(const uint8_t *packed,size_t pixel){return index_at(packed,pixel);}
static void store(uint8_t *packed,size_t pixel,unsigned value){
    size_t bit=pixel*6,byte=bit/8;unsigned shift=bit%8;
    packed[byte]|=(uint8_t)(value<<shift);
    if(shift>2)packed[byte+1]|=(uint8_t)(value>>(8-shift));
}
bool f75_sprite_begin(f75_sprite_decoder *decoder,const uint8_t *source,size_t bytes,uint8_t *out,size_t capacity,size_t pixels){
    if(!decoder||!source||!out||!bytes||bytes>6400||!pixels||pixels>6400)return false;
    size_t needed=(pixels*6+7)/8;if(capacity<needed)return false;
    for(size_t i=0;i<needed;i++)out[i]=0;
    *decoder=(f75_sprite_decoder){.data=source,.bytes=bytes,.pixels=pixels};
    return true;
}
bool f75_sprite_step(f75_sprite_decoder *input,uint8_t *out,size_t capacity,size_t through_pixel){
    if(!input||!out||input->failed||!input->data||!input->pixels||input->pixels>6400||
       through_pixel>input->pixels||capacity<(input->pixels*6+7)/8)return false;
    while(input->position<through_pixel){
        if(input->remaining){
            /* Four aligned palette indices occupy three whole bytes. Copy
             * that group directly, including overlapping LZ runs, without
             * unpacking and repacking each six-bit pixel. No larger cache. */
            if(!(input->position&3u)&&!(input->distance&3u)&&input->remaining>=4&&through_pixel-input->position>=4){
                size_t to=input->position*3/4,from=(input->position-input->distance)*3/4;
                out[to]=out[from];out[to+1]=out[from+1];out[to+2]=out[from+2];
                input->position+=4;input->remaining-=4;continue;
            }
            store(out,input->position,index_at(out,input->position-input->distance));
            input->position++;input->remaining--;continue;
        }
        unsigned literal,value,length;
        if(!take(input,1,&literal))goto malformed;
        if(literal){if(!take(input,6,&value))goto malformed;store(out,input->position++,value);}
        else {
            if(!take(input,11,&value)||!take(input,5,&length))goto malformed;
            size_t distance=value+1;length+=3;
            if(distance>input->position||length>input->pixels-input->position)goto malformed;
            input->distance=(unsigned)distance;input->remaining=length;
        }
    }
    if(input->position==input->pixels){
        if(input->remaining||input->bytes*8-input->bit>=8)goto malformed;
        unsigned padding;
        if(!take(input,(unsigned)(input->bytes*8-input->bit),&padding)||padding)goto malformed;
    }
    return true;
malformed:
    input->failed=true;return false;
}
bool f75_sprite_decode(const uint8_t *source,size_t bytes,uint8_t *out,size_t capacity,size_t pixels){
    f75_sprite_decoder decoder;
    return f75_sprite_begin(&decoder,source,bytes,out,capacity,pixels)&&f75_sprite_step(&decoder,out,capacity,pixels);
}
