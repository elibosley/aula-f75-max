#include "f75_core.h"
#include "f75_navigation.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    f75_config c;f75_defaults(&c);assert(f75_config_valid(&c));
    f75_state s;f75_init(&s,&c,0);
    f75_state automatic;f75_init(&automatic,NULL,0);
    assert(automatic.config.os_auto_mask==0x1f);
    assert(f75_detect_os(&automatic,0,F75_WINDOWS));
    assert(f75_map_usage(&automatic,0xe2)==0xe2&&f75_map_usage(&automatic,0x39)==0xe0);
    assert(f75_set_os(&automatic,F75_MAC));
    assert(!f75_detect_os(&automatic,0,F75_WINDOWS)&&automatic.config.os[0]==F75_MAC);
    assert(f75_detect_os(&automatic,1,F75_WINDOWS)&&automatic.config.os[0]==F75_MAC);
    f75_navigation nav;f75_navigation_init(&nav);
    assert(nav.wheel_divisor==1);
    f75_back(&s,&nav,0);assert(nav.page==F75_HOME);
    f75_open_page(&nav,F75_MENU);
    f75_turn(&s,&nav,1,100);assert(nav.cursor==1&&nav.wheel_pending==0);
    f75_turn(&s,&nav,-1,110);assert(nav.cursor==0&&nav.wheel_pending==0);
    f75_turn(&s,&nav,1,1000);assert(nav.cursor==1);
    nav.wheel_divisor=0;f75_turn(&s,&nav,1,1010);assert(nav.cursor==2);
    f75_navigation_init(&nav);
    assert(f75_turn(&s,&nav,1,0)==F75_UI_HOST_ACTION&&nav.volume==44);
    f75_press(&s,&nav,1);assert(nav.page==F75_MENU);f75_turn(&s,&nav,-1,2);assert(nav.cursor==5);f75_turn(&s,&nav,-1,3);assert(nav.cursor==4);f75_press(&s,&nav,3);assert(nav.page==F75_FOCUS);
    assert(f75_press(&s,&nav,3)==F75_UI_TIMER_TOGGLE);f75_open_page(&nav,F75_POWER);
    f75_turn(&s,&nav,1,4);f75_press(&s,&nav,5);assert(s.config.power==F75_ENDURANCE);
    f75_set_control_layer(&s,true);f75_control_key(&s,&nav,0x1f,6);assert(nav.page==F75_KEYS);f75_control_key(&s,&nav,0x16,7);assert(f75_control_key(&s,&nav,0x16,7)==F75_UI_SAVE);f75_set_control_layer(&s,false);
    s.config.power=F75_BALANCED;
    f75_open_page(&nav,F75_LIGHTING);nav.cursor=1;s.config.brightness=95;f75_press(&s,&nav,8);assert(nav.editing&&s.config.brightness==95);
    for(unsigned t=100;t<300;t+=20)f75_turn(&s,&nav,1,t);
    assert(s.config.brightness==100&&nav.cursor==1&&f75_config_valid(&s.config));
    f75_turn(&s,&nav,-1,300);assert(s.config.brightness==99);
    f75_turn(&s,&nav,-1,1000);assert(s.config.brightness==98);
    f75_back(&s,&nav,1001);assert(!nav.editing&&nav.page==F75_LIGHTING);s.config.brightness=28;
    f75_open_page(&nav,F75_MENU);nav.wheel_divisor=2;
    f75_turn(&s,&nav,1,1100);assert(nav.cursor==0&&nav.wheel_pending==1);
    f75_turn(&s,&nav,-1,1120);assert(nav.cursor==0&&nav.wheel_pending==-1);
    f75_turn(&s,&nav,-1,1140);assert(nav.cursor==5&&nav.wheel_pending==0);
    f75_turn(&s,&nav,1,1200);f75_turn(&s,&nav,1,1600);assert(nav.cursor==5&&nav.wheel_pending==1);
    f75_set_control_layer(&s,true);f75_control_key(&s,&nav,0x51,1601);assert(nav.cursor==0&&nav.wheel_pending==0);f75_set_control_layer(&s,false);
    for(unsigned os=0;os<3;os++){assert(f75_set_os(&s,(f75_os)os));assert(f75_map_usage(&s,0x39)==(os==F75_MAC?0xe3:0xe0));assert(f75_map_usage(&s,0xe0)==0x39);assert(f75_map_usage(&s,0xe4)==(os==F75_MAC?0xe7:0xe4));}
    assert(f75_set_os(&s,F75_MAC));assert(f75_map_usage(&s,0xe2)==0xe3);assert(f75_map_usage(&s,0xe3)==0xe2);
    f75_set_caps_swap(&s,false);assert(f75_map_usage(&s,0x39)==0x39&&f75_map_usage(&s,0xe0)==0xe3);f75_set_caps_swap(&s,true);
    uint32_t epoch=s.release_epoch;f75_set_control_layer(&s,true);assert(s.release_epoch==epoch+1);f75_set_control_layer(&s,false);
    assert(f75_pair_request(&s,2,100));assert(!f75_pair_confirm(&s,1199,200));uint32_t token=f75_pair_confirm(&s,1200,1500);assert(token);assert(!(s.config.bonded_mask&(1u<<2)));
    assert(!f75_host_ack(&s,3,token));assert(!f75_host_ack(&s,2,token+1));assert(f75_host_ack(&s,2,token));assert(s.config.active_host==2);assert(s.config.bonded_mask&(1u<<2));
    assert(f75_pair_request(&s,1,3000));token=f75_pair_confirm(&s,1200,4000);f75_tick(&s,34000);assert(s.pairing==F75_PAIR_TIMEOUT);assert(!f75_host_ack(&s,1,token));
    f75_press(&s,&nav,34001);assert(s.pairing==F75_PAIR_CONFIRM);f75_back(&s,&nav,34002);assert(s.pairing==F75_PAIR_IDLE);
    f75_pair_cancel(&s);token=f75_switch_host(&s,0,35000);assert(token);assert(f75_host_ack(&s,0,token));
    f75_budget b=f75_power_budget(&s,35000,5,false);assert(b.rgb==0&&b.animation_fps==0);assert(f75_map_usage(&s,0x39)==0xe3);
    b=f75_power_budget(&s,100000,78,false);assert(b.stage==F75_OFF&&b.rgb==0&&b.screen==0);
    f75_activity(&s,UINT32_MAX-100);b=f75_power_budget(&s,100,78,false);assert(b.stage==F75_ACTIVE);
    uint8_t a[F75_RECORD_BYTES],other[F75_RECORD_BYTES];uint32_t generation;f75_config decoded;
    f75_record_encode(&s.config,10,a);assert(f75_record_decode(a,&decoded,&generation));assert(generation==10&&decoded.caps_swap);
    s.config.brightness=17;f75_record_encode(&s.config,11,other);assert(f75_record_select(a,other,&decoded,&generation));assert(generation==11&&decoded.brightness==17);
    other[30]^=1;assert(f75_record_select(a,other,&decoded,&generation));assert(generation==10);
    a[90]^=1;assert(!f75_record_select(a,other,&decoded,&generation));
    f75_record_encode(&s.config,UINT32_MAX,a);f75_record_encode(&s.config,0,other);assert(f75_record_select(a,other,&decoded,&generation));assert(generation==0);
    s.config.companion=2;f75_record_encode(&s.config,11,a);assert(a[4]==6&&a[127]==2);
    assert(f75_record_decode(a,&decoded,&generation)&&decoded.companion==2);
    a[4]=5;for(unsigned i=0,crc=f75_crc32(a,156);i<4;i++)a[156+i]=(uint8_t)(crc>>(i*8));
    assert(f75_record_decode(a,&decoded,&generation)&&decoded.companion==3);
    s.config.companion=3;
    s.config.light_mode=1;f75_record_encode(&s.config,12,a);assert(a[4]==6&&f75_record_decode(a,&decoded,&generation)&&decoded.light_mode==1);
    FILE *legacy=fopen("tests/fixtures/settings-v1.bin","rb");assert(legacy);assert(fread(a,1,sizeof(a),legacy)==sizeof(a));fclose(legacy);
    assert(f75_record_decode(a,&decoded,&generation)&&generation==7&&decoded.light_mode==0&&decoded.caps_swap&&decoded.face==3);
    legacy=fopen("tests/fixtures/settings-v2.bin","rb");assert(legacy);assert(fread(a,1,sizeof(a),legacy)==sizeof(a));fclose(legacy);
    assert(f75_record_decode(a,&decoded,&generation)&&generation==8&&decoded.light_mode==1&&decoded.face==3);
    s.config.face=0;f75_record_encode(&s.config,13,a);assert(f75_record_decode(a,&decoded,&generation)&&decoded.face==0);
    f75_open_page(&nav,F75_KEYS);nav.cursor=3;f75_press(&s,&nav,2000);assert(s.config.light_mode==0);
    f75_set_os(&s,F75_ANDROID);f75_record_encode(&s.config,14,a);assert(a[4]==6&&f75_record_decode(a,&decoded,&generation)&&decoded.os[0]==F75_ANDROID);
    f75_open_page(&nav,F75_KEYS);nav.cursor=0;f75_press(&s,&nav,2001);assert(s.config.os_auto_mask&1);f75_press(&s,&nav,2002);assert(s.config.os[0]==F75_MAC&&!(s.config.os_auto_mask&1));f75_press(&s,&nav,2003);assert(s.config.os[0]==F75_WINDOWS);f75_press(&s,&nav,2004);assert(s.config.os[0]==F75_ANDROID);
    f75_defaults(&s.config);f75_open_page(&nav,F75_LIGHTING);nav.cursor=3;f75_press(&s,&nav,2100);assert(!strcmp(f75_color_name(&s.config),"Rose"));nav.cursor=4;assert(f75_press(&s,&nav,2101)==F75_UI_SAVE);
    f75_open_page(&nav,F75_SCREEN);assert(nav.page==F75_SCREEN);s.config.companion=3;
    f75_press(&s,&nav,2200);assert(s.config.companion==0);nav.cursor=4;assert(f75_press(&s,&nav,2201)==F75_UI_SAVE);
    f75_back(&s,&nav,2202);assert(nav.page==F75_MENU);
    printf("C core checks passed. config=%zu bytes state=%zu bytes tile=%u bytes\n",sizeof(f75_config),sizeof(f75_state),128u*F75_TILE_ROWS*2u);
    return 0;
}
