#ifndef F75_SPRITE_H
#define F75_SPRITE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
uint8_t f75_sprite_index(const uint8_t *packed,size_t pixel);
typedef struct {
    const uint8_t *data;
    size_t bytes,bit,position,pixels;
    unsigned distance,remaining;
    bool failed;
} f75_sprite_decoder;
bool f75_sprite_begin(f75_sprite_decoder *decoder,const uint8_t *source,size_t bytes,uint8_t *output,size_t capacity,size_t pixels);
bool f75_sprite_step(f75_sprite_decoder *decoder,uint8_t *output,size_t capacity,size_t through_pixel);
bool f75_sprite_decode(const uint8_t *source,size_t bytes,uint8_t *output,size_t capacity,size_t pixels);
#endif
