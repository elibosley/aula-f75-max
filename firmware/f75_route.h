#pragma once
#include <stdint.h>
#include <stdbool.h>
enum { F75_ROUTE_PAGE=1024,F75_ROUTE_BYTES=2048,F75_ROUTE_ENTRY=16 };
typedef struct {uint32_t sequence;unsigned offset;uint8_t slot;bool valid;} f75_route_record;
f75_route_record f75_route_latest(const uint8_t *pages);
void f75_route_encode(uint8_t out[16],uint32_t sequence,uint8_t slot);
bool f75_route_plan(const uint8_t *pages,uint8_t slot,unsigned *offset,bool *erase,uint32_t *sequence);
