#include "f75_custom.h"
#include <assert.h>
#include <string.h>
int main(void) {
    f75_config config;f75_defaults(&config);
    uint8_t record[F75_RECORD_BYTES];f75_record_encode(&config,1,record);
    assert(record[130]==F75_MODEL_ID);
    f75_custom custom;f75_custom_defaults(&custom);
    custom.keys[0][F75_FN_KEY]=4;assert(!f75_custom_valid(&custom));
    custom.keys[0][F75_FN_KEY]=0;
    custom.keys[0][F75_FN_KEY==65?71:65]=4;assert(f75_custom_valid(&custom));
    uint8_t pwm[270]={0};f75_custom_indicators(&custom,false,true,100,pwm);
    unsigned fn_led=(F75_FN_KEY%6)*15+F75_FN_KEY/6;
    for(unsigned channel=0;channel<3;++channel){
        assert(pwm[channel*90+fn_led]==custom.fn_color[channel]*127u/255u);
        assert(pwm[channel*90+(fn_led==85?86:85)]==0);
    }
    return 0;
}
