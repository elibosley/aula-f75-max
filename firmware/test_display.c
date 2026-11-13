#include "f75_display.h"
_Static_assert(sizeof(f75_view)==224,"Display ABI size must remain stable");
_Static_assert(offsetof(f75_view,highlight_y)==194,"Existing display offsets must remain stable");
_Static_assert(offsetof(f75_view,visitor_x)==222,"Existing display offsets must remain stable");
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "f75_visitor_assets.h"

static void dirty_mask_covers_pixels(f75_view a,f75_view b){
    uint16_t first[128*128],second[128*128];
    uint16_t dirty=f75_changed_tiles(&a,&b);
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&a,y,8,first+y*128,1024));
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&b,y,8,second+y*128,1024));
    for(unsigned y=0;y<128;y++)for(unsigned x=0;x<128;x++)if(first[y*128+x]!=second[y*128+x])assert(dirty&(1u<<(y/8)));
}

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
    f75_view changed=view;assert(f75_changed_tiles(&view,&view)==0);
    for(unsigned i=0;i<16;i++){
        unsigned pixels=0;
        for(unsigned at=0;at<f75_visitor_lengths[i];++at){pixels+=(f75_visitor_frames[i][at]>>4)+1;assert((f75_visitor_frames[i][at]&15)<8);}
        assert(pixels==400);
        changed=view;changed.visitor=true;changed.visitor_frame=(uint8_t)i;changed.visitor_x=79;
        dirty_mask_covers_pixels(view,changed);
        changed.visitor_x=95;changed.visitor_flip=true;dirty_mask_covers_pixels(view,changed);
    }
    changed=view;changed.pet_bob=2;dirty_mask_covers_pixels(view,changed);
    changed=view;changed.pet_character=1;dirty_mask_covers_pixels(view,changed);
    changed=view;changed.pet_frame=2;dirty_mask_covers_pixels(view,changed);
    changed=view;changed.pet_effect=1;changed.pet_phase=4;dirty_mask_covers_pixels(view,changed);
    changed=view;changed.pet_wpm=100;changed.pet_mode=2;dirty_mask_covers_pixels(view,changed);
    changed=view;strcpy(changed.clock,"08:00");dirty_mask_covers_pixels(view,changed);
    changed=view;changed.light_mode=!view.light_mode;dirty_mask_covers_pixels(view,changed);
    changed=view;changed.pet_info=true;changed.info_progress=50;dirty_mask_covers_pixels(view,changed);
    changed=view;strcpy(changed.status_left,"BT2");dirty_mask_covers_pixels(view,changed);
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
    for(unsigned theme=0;theme<2;theme++)for(unsigned editing=0;editing<2;editing++){
        menu.light_mode=theme!=0;menu.editing=editing!=0;menu.motion=true;
        for(int y=-3;y<=63;y++){
            menu.highlight_y=(int16_t)y;changed=menu;changed.highlight_y=(int16_t)(y+1);
            dirty_mask_covers_pixels(menu,changed);
        }
        assert(f75_changed_tiles(&menu,&menu)==0);
        changed=menu;strcpy(changed.rows[2],"Brightness: 100%");dirty_mask_covers_pixels(menu,changed);
        changed=menu;changed.content_x=-12;dirty_mask_covers_pixels(menu,changed);
        changed=menu;strcpy(changed.footer,"Editing value");dirty_mask_covers_pixels(menu,changed);
        changed=menu;strcpy(changed.title,"Lighting");dirty_mask_covers_pixels(menu,changed);
        changed=menu;changed.selected=255;dirty_mask_covers_pixels(menu,changed);
        changed=menu;changed.light_mode=!menu.light_mode;assert(f75_changed_tiles(&menu,&changed)==0xffffu);
    }
    for(unsigned count=2;count<=6;count++){
        menu.menu_count=(uint8_t)count;
        for(unsigned position=0;position<count;position++){
            menu.menu_position=(uint8_t)position;changed=menu;changed.menu_position=(uint8_t)((position+1)%count);
            dirty_mask_covers_pixels(menu,changed);
        }
        changed=menu;changed.menu_count=0;dirty_mask_covers_pixels(menu,changed);
    }
    menu.menu_count=0;
    menu.motion=false;menu.editing=false;menu.light_mode=false;
    for(unsigned y=0;y<128;y+=8)assert(f75_render_tile(&menu,y,8,whole+y*128,1024));
    strcpy(menu.status_left,"BT1");strcpy(menu.status_right,"Offline");
    for(unsigned y=0;y<128;y++){assert(f75_render_tile(&menu,y,1,row,128));assert(!memcmp(row,whole+y*128,sizeof(row)));}
    menu.rows[4][0]='f';differs=false;
    for(unsigned y=89;y<103;y++){assert(f75_render_tile(&menu,y,1,row,128));if(memcmp(row,whole+y*128,sizeof(row)))differs=true;}assert(differs);
    f75_motion_update(&motion,2,4,1,1100,true);assert(motion.selection==60*256);
    puts("RGB565 renderer: five menu rows, title header, hidden transport, tile seams, and bounds passed.");return 0;
}
