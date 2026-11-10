#include "f75_display.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(int argc,char **argv){
    f75_motion motion={0};
    f75_motion paused={0};f75_motion_update(&paused,1,0,1,0,false);
    f75_motion_nudge(&paused,1,1000);f75_motion_update(&paused,1,0,1,1000,false);assert(paused.selection==2*256);
    f75_motion_update(&motion,1,0,1,0,false);assert(!f75_motion_active(&motion));
    f75_motion_nudge(&motion,1,0);assert(motion.selection==2*256&&motion.selected==0);
    f75_motion_update(&motion,1,1,1,100,false);assert(motion.selected==1&&motion.selection!=15*256);
    f75_motion_update(&motion,1,2,1,116,false);assert(motion.selected==2);
    f75_motion_update(&motion,1,0,-1,132,false);assert(motion.selected==0);
    for(unsigned t=148;t<=500;t+=16)f75_motion_update(&motion,1,0,1,t,false);
    assert(!f75_motion_active(&motion));
    f75_motion_update(&motion,2,3,1,520,false);assert(motion.slide==12*256);
    f75_motion_update(&motion,2,2,-1,530,true);assert(!f75_motion_active(&motion)&&motion.selection==30*256);
    f75_motion_update(&motion,2,0,-1,UINT32_MAX-10,true);
    f75_motion_update(&motion,2,1,1,5,false);assert(motion.selected==1);
    f75_motion_update(&motion,2,1,1,1000,false);assert(!f75_motion_active(&motion));
    assert(argc==2);FILE *out=fopen(argv[1],"wb");assert(out);
    f75_view view={.status_left="USB",.status_right="78%",.clock="12:48",.host_label="USB CABLE",.os="MAC",.footer="PRESS FOR MENU",.home=true,.caps_swap=true};
    uint16_t buffer[128*F75_TILE_ROWS+2];buffer[0]=0xa55a;buffer[128*F75_TILE_ROWS+1]=0x5aa5;
    fprintf(out,"P6\n128 128\n255\n");
    for(unsigned y=0;y<128;y+=F75_TILE_ROWS){
        assert(f75_render_tile(&view,(uint8_t)y,F75_TILE_ROWS,buffer+1,128*F75_TILE_ROWS));
        for(unsigned i=1;i<=128*F75_TILE_ROWS;i++){
            uint16_t pixel=buffer[i];uint8_t rgb[3]={(uint8_t)(((pixel>>11)&31)*255/31),(uint8_t)(((pixel>>5)&63)*255/63),(uint8_t)((pixel&31)*255/31)};
            assert(fwrite(rgb,1,3,out)==3);
        }
        assert(buffer[0]==0xa55a&&buffer[128*F75_TILE_ROWS+1]==0x5aa5);
    }
    assert(!f75_render_tile(&view,127,8,buffer,128*8));assert(!f75_render_tile(&view,0,9,buffer,128*8));assert(!f75_render_tile(&view,0,8,buffer,10));
    assert(!f75_render_tile(NULL,0,8,buffer,128*8));fclose(out);
    view.light_mode=true;assert(f75_render_tile(&view,0,8,buffer,128*8)&&buffer[0]==0xef7b);
    view.timer=true;view.timer_progress=255;view.alert_pulse=true;assert(f75_render_tile(&view,0,8,buffer,128*8)&&buffer[0]==0xded6);
    view.light_mode=false;assert(f75_render_tile(&view,0,8,buffer,128*8)&&buffer[0]==0x2349);
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&view,(uint8_t)y,8,buffer,128*8));
    view.timer=false;view.home=true;view.face=3;
    for(unsigned frame=0;frame<6;frame++)for(unsigned effect=0;effect<=4;effect++)for(unsigned theme=0;theme<2;theme++){
        view.pet_frame=(uint8_t)frame;view.pet_effect=(uint8_t)effect;view.pet_phase=15;view.pet_bob= -1;view.pet_wpm=999;view.pet_mode=3;view.light_mode=theme!=0;
        for(unsigned y=0;y<128;y+=8){buffer[0]=0xa55a;buffer[128*8+1]=0x5aa5;assert(f75_render_tile(&view,(uint8_t)y,8,buffer+1,128*8));assert(buffer[0]==0xa55a&&buffer[128*8+1]==0x5aa5);}
    }
    /* A time update must repaint only the clock, leaving the pet, pace,
       transport and priority footer untouched, including in the light theme. */
    uint16_t clock_before[128*128],clock_after[128*128],clock_row[128];
    for(unsigned theme=0;theme<2;theme++){
        view.light_mode=theme!=0;view.pet_effect=0;view.pet_bob=2;view.pet_wpm=999;
        strcpy(view.clock,"12:34");
        for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&view,y,8,clock_before+y*128,1024));
        strcpy(view.clock,"03:00");unsigned changes=0;
        for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&view,y,8,clock_after+y*128,1024));
        for(unsigned y=0;y<128;y++){
            assert(f75_render_tile(&view,y,1,clock_row,128));assert(!memcmp(clock_row,clock_after+y*128,sizeof(clock_row)));
            for(unsigned x=0;x<128;x++)if(clock_before[y*128+x]!=clock_after[y*128+x]){assert(x>=6&&x<=30&&y>=75&&y<100);changes++;}
        }
        assert(changes>10);
    }
    /* Cardinal times point in the expected directions on the desk clock. */
    strcpy(view.clock,"03:00");assert(f75_render_tile(&view,80,8,buffer,1024));
    assert(buffer[7*128+23]==0x1125&&buffer[18]==0x1125);
    strcpy(view.clock,"06:00");assert(f75_render_tile(&view,88,8,buffer,1024));
    assert(buffer[4*128+18]==0x1125);
    /* The home header carries the effective OS icon, not profile metadata. */
    view.os_source=0;
    for(unsigned y=0;y<24;y+=8)assert(f75_render_tile(&view,y,8,clock_before+y*128,1024));
    for(unsigned source=1;source<=2;source++){
        view.os_source=source;
        for(unsigned y=0;y<24;y+=8){assert(f75_render_tile(&view,y,8,buffer,1024));assert(!memcmp(buffer,clock_before+y*128,2048));}
    }
    /* Font coverage must blend at edges and stay identical across tile seams. */
    f75_view typography={.status_left="USB",.status_right="100%",.title="Mixed case",.rows={"Agyp Quick text","WWWWWWWWWWWWWWWWWWW"},.footer="Press for menu",.selected=255};
    uint16_t whole[128*128],row[128];unsigned blended=0;
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&typography,(uint8_t)y,8,whole+y*128,128*8));
    for(unsigned i=0;i<128*128;i++)if(whole[i]!=0x08a2&&whole[i]!=0xe7bc&&whole[i]!=0xaf5a&&whole[i]!=0x9573&&whole[i]!=0x29e6)blended++;
    assert(blended>20);
    for(unsigned y=0;y<128;y++){assert(f75_render_tile(&typography,(uint8_t)y,1,row,128));assert(!memcmp(row,whole+y*128,sizeof(row)));}
    typography.title[0]='m';assert(f75_render_tile(&typography,7,1,row,128));
    bool differs=false;for(unsigned y=6;y<19;y++){assert(f75_render_tile(&typography,(uint8_t)y,1,row,128));if(memcmp(row,whole+y*128,sizeof(row)))differs=true;}assert(differs);
    f75_view menu={.title="Menu",.rows={"Devices","Keys","Lighting","Power","Focus"},.selected=4,.status_left="USB",.status_right="Ready"};
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&menu,y,8,whole+y*128,1024));
    strcpy(menu.status_left,"BT1");strcpy(menu.status_right,"Offline");
    for(unsigned y=0;y<128;y++){assert(f75_render_tile(&menu,y,1,row,128));assert(!memcmp(row,whole+y*128,sizeof(row)));}
    menu.rows[4][0]='f';differs=false;
    for(unsigned y=89;y<103;y++){assert(f75_render_tile(&menu,y,1,row,128));if(memcmp(row,whole+y*128,sizeof(row)))differs=true;}assert(differs);
    f75_motion_update(&motion,2,4,1,1100,true);assert(motion.selection==60*256);
    puts("RGB565 renderer: five menu rows, title header, hidden transport, tile seams, and bounds passed.");return 0;
}
