#include "f75_sprite.h"
#include "f75_core.h"
#include "companion_assets.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
int main(void){
    uint8_t guarded[4802],decoded[6400];memset(guarded,0xa5,sizeof(guarded));
    for(unsigned character=0;character<4;character++)for(unsigned frame=0;frame<12;frame++){
        const uint8_t *data=f75_companion_streams[character][frame];size_t bytes=f75_companion_lengths[character][frame];
        assert(f75_sprite_decode(data,bytes,guarded+1,4800,6400));
        for(unsigned i=0;i<6400;i++)decoded[i]=f75_sprite_index(guarded+1,i);
        assert(f75_crc32(decoded,6400)==f75_companion_checksums[character][frame]);
        assert(guarded[0]==0xa5&&guarded[4801]==0xa5);
        for(unsigned i=0;i<6400;i++)assert(decoded[i]<64);
        assert(!f75_sprite_decode(data,bytes-1,guarded+1,4800,6400));
    }
    assert(!f75_sprite_decode(NULL,1,guarded+1,4800,6400));
    assert(!f75_sprite_decode(guarded,1,NULL,4800,6400));
    assert(!f75_sprite_decode(guarded,6401,guarded+1,4800,6400));
    assert(!f75_sprite_decode(guarded,1,guarded+1,4800,6401));
    uint32_t random=75;uint8_t malformed[128];
    for(unsigned trial=0;trial<1000;trial++){
        for(unsigned i=0;i<sizeof(malformed);i++){random^=random<<13;random^=random>>17;random^=random<<5;malformed[i]=(uint8_t)random;}
        (void)f75_sprite_decode(malformed,sizeof(malformed),guarded+1,4800,6400);
        assert(guarded[0]==0xa5&&guarded[4801]==0xa5);
    }
    puts("48 compressed sprite frames: exact decode, palette bounds, truncation, malformed input and output guards passed.");
}
