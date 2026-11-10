#include "f75_display.h"
#include "font_data.h"
#include "f75_icons.h"
#include "companion_assets.h"
#include "f75_sprite.h"

typedef struct { uint8_t y,rows;uint16_t *pixels; } tile;
static void dot(tile *t,int x,int y,uint16_t color){if(x>=0&&x<128&&y>=t->y&&y<t->y+t->rows)t->pixels[(y-t->y)*128+x]=color;}
static void rect(tile *t,int x,int y,int w,int h,uint16_t color){
    int right=x+w,bottom=y+h;
    if(x<0)x=0;
    if(right>128)right=128;
    if(y<t->y)y=t->y;
    if(bottom>t->y+t->rows)bottom=t->y+t->rows;
    if(x>=right||y>=bottom)return;
    for(int yy=y;yy<bottom;yy++){
        uint16_t *out=t->pixels+(yy-t->y)*128+x;
        for(int xx=x;xx<right;xx++)*out++=color;
    }
}
static void soft_rect(tile *t,int x,int y,int w,int h,uint16_t color){
    /* Three-pixel corners remain identical across clipped tile boundaries. */
    rect(t,x+3,y,w-6,1,color);rect(t,x+1,y+1,w-2,2,color);
    rect(t,x,y+3,w,h-6,color);
    rect(t,x+1,y+h-3,w-2,2,color);rect(t,x+3,y+h-1,w-6,1,color);
}
static void heart(tile *t,int x,int y,uint16_t color){
    static const uint8_t rows[]={0x36,0x7f,0x7f,0x3e,0x1c,0x08};
    for(unsigned yy=0;yy<6;yy++)for(unsigned xx=0;xx<7;xx++)if(rows[yy]&(1u<<(6-xx)))dot(t,x+(int)xx,y+(int)yy,color);
}
static void sparkle(tile *t,int x,int y,uint16_t color){
    rect(t,x-2,y,5,1,color);rect(t,x,y-2,1,5,color);
}
static void line(tile *t,int x,int y,int end_x,int end_y,uint16_t color){
    int dx=end_x>x?end_x-x:x-end_x,sx=x<end_x?1:-1;
    int dy=end_y>y?y-end_y:end_y-y,sy=y<end_y?1:-1,error=dx+dy;
    for(;;){dot(t,x,y,color);if(x==end_x&&y==end_y)break;int twice=error*2;
        if(twice>=dy){error+=dy;x+=sx;}if(twice<=dx){error+=dx;y+=sy;}}
}
static const f75_glyph *glyph(unsigned char c,int scale){
    const f75_glyph *font=scale>1?f75_font_large:scale==0?f75_font_compact:f75_font_small;
    return &font[c<128&&font[c].advance?c:'?'];
}
static int text_width(const char *s,unsigned limit,int scale){int width=0;for(unsigned n=0;n<limit&&s[n];n++)width+=glyph((unsigned char)s[n],scale)->advance;return width;}
/* Exact /15 for the 0..952 weighted color range, without M0 software division. */
static unsigned color_div15(unsigned value){return (value*0x8889u)>>19;}
static void blend_dot(tile *t,int x,int y,uint16_t color,unsigned alpha){
    if(!alpha||x<0||x>=128||y<t->y||y>=t->y+t->rows)return;
    if(alpha==15){dot(t,x,y,color);return;}
    uint16_t bg=t->pixels[(y-t->y)*128+x];unsigned inverse=15-alpha;
    unsigned r=color_div15(((color>>11)&31)*alpha+((bg>>11)&31)*inverse+7);
    unsigned g=color_div15(((color>>5)&63)*alpha+((bg>>5)&63)*inverse+7);
    unsigned b=color_div15((color&31)*alpha+(bg&31)*inverse+7);
    dot(t,x,y,(uint16_t)((r<<11)|(g<<5)|b));
}
static void draw_glyph(tile *t,const f75_glyph *g,int x,int y,int scale,uint16_t color){
    const uint8_t *pixels=scale>1?f75_font_large_pixels:scale==0?f75_font_compact_pixels:f75_font_small_pixels;
    int left=x+g->x,top=y+g->y;
    int first_y=t->y>top?t->y-top:0,last_y=t->y+t->rows-top;
    int first_x=left<0?-left:0,last_x=128-left;
    if(last_y>g->height)last_y=g->height;
    if(last_x>g->width)last_x=g->width;
    for(int yy=first_y;yy<last_y;yy++)for(int xx=first_x;xx<last_x;xx++){
        unsigned index=(unsigned)yy*g->width+(unsigned)xx;uint8_t packed=pixels[g->offset+index/2];
        blend_dot(t,left+xx,top+yy,color,index%2?packed&15:packed>>4);
    }
}
static void text(tile *t,const char *s,unsigned limit,int x,int y,int scale,uint16_t color){
    int available=121-x;bool clipped=text_width(s,limit,scale)>available;
    int ellipsis=3*glyph('.',scale)->advance;if(clipped)available-=ellipsis;
    int used=0;
    for(unsigned n=0;n<limit&&s[n];n++){
        const f75_glyph *g=glyph((unsigned char)s[n],scale);if(used+g->advance>available)break;
        draw_glyph(t,g,x+used,y,scale,color);used+=g->advance;
    }
    if(clipped)for(unsigned i=0;i<3;i++){const f75_glyph *g=glyph('.',scale);draw_glyph(t,g,x+used,y,scale,color);used+=g->advance;}
}
static void centered(tile *t,const char *s,unsigned limit,int y,int scale,uint16_t color){int x=(128-text_width(s,limit,scale))/2;text(t,s,limit,x<7?7:x,y,scale,color);}
static int32_t magnitude(int32_t n){return n<0?-n:n;}
static uint16_t readable_accent(uint16_t color,bool light){
    unsigned r=((color>>11)&31)*255/31,g=((color>>5)&63)*255/63,b=(color&31)*255/31;
    unsigned luminance=(54*r+183*g+19*b)>>8;
    if(light&&luminance>90){r=r*90/luminance;g=g*90/luminance;b=b*90/luminance;}
    else if(!light&&luminance<160){unsigned mix=(160-luminance)*255/(255-luminance);r=(r*(255-mix)+255*mix)/255;g=(g*(255-mix)+255*mix)/255;b=(b*(255-mix)+255*mix)/255;}
    return (uint16_t)(((r>>3)<<11)|((g>>2)<<5)|(b>>3));
}
static void os_icon(tile *t,const f75_view *v,int x,int y,uint16_t ink){
    unsigned kind=v->os[0]=='M'?0:v->os[0]=='W'?1:2;
    if(v->os[0]!='M'&&v->os[0]!='W'&&v->os[0]!='A')return;
    for(unsigned yy=0;yy<F75_OS_ICON_SIZE;yy++)for(unsigned xx=0;xx<F75_OS_ICON_SIZE;xx++){
        unsigned index=yy*F75_OS_ICON_SIZE+xx;uint8_t packed=f75_os_icon_alpha[kind][index/2];
        blend_dot(t,x+(int)xx,y+(int)yy,ink,index%2?packed&15:packed>>4);
    }
}
static void desk_clock(tile *t,const f75_view *v,uint16_t rose){
    /* A stationary little alarm clock sits beside the native-size keyboard.
       Hands use the same synchronized local time as the other home faces. */
    static const int8_t sine[60]={0,7,13,20,26,32,38,43,48,52,55,58,61,63,64,64,64,63,61,58,55,52,48,43,38,32,26,20,13,7,0,-7,-13,-20,-26,-32,-38,-43,-48,-52,-55,-58,-61,-63,-64,-64,-64,-63,-61,-58,-55,-52,-48,-43,-38,-32,-26,-20,-13,-7};
    const int cx=18,cy=87;const uint16_t outline=0x4aeb,face=0xef7b,hands=0x1125;
    rect(t,10,72,4,1,rose);rect(t,8,73,7,2,rose);
    rect(t,23,72,4,1,rose);rect(t,22,73,7,2,rose);
    rect(t,11,99,3,3,outline);rect(t,22,99,3,3,outline);
    int first=t->y>75?t->y:75,last=t->y+t->rows<100?t->y+t->rows:100;
    for(int y=first;y<last;y++)for(int x=6;x<=30;x++){
        int distance=(x-cx)*(x-cx)+(y-cy)*(y-cy);
        if(distance<=144)dot(t,x,y,distance>121?outline:distance>90?rose:face);
    }
    for(unsigned i=0;i<60;i+=5){int x=cx+sine[i]*8/64,y=cy-sine[(i+15)%60]*8/64;dot(t,x,y,outline);}
    if(v->clock[0]<'0'||v->clock[0]>'2'||v->clock[1]<'0'||v->clock[1]>'9'||v->clock[2]!=':'||
       v->clock[3]<'0'||v->clock[3]>'5'||v->clock[4]<'0'||v->clock[4]>'9'){
        text(t,"--",2,cx-4,cy-3,1,outline);return;
    }
    unsigned hour=(unsigned)(v->clock[0]-'0')*10u+(unsigned)(v->clock[1]-'0');
    unsigned minute=(unsigned)(v->clock[3]-'0')*10u+(unsigned)(v->clock[4]-'0');
    unsigned hour_tick=(hour%12)*5+minute/12;
    line(t,cx,cy,cx+sine[hour_tick]*5/64,cy-sine[(hour_tick+15)%60]*5/64,hands);
    line(t,cx,cy,cx+sine[minute]*7/64,cy-sine[(minute+15)%60]*7/64,hands);
    dot(t,cx,cy,rose);
}
static void pet_sprite(tile *t,const f75_view *v,uint16_t accent){
    static uint8_t sprite[4800],cached_frame=255,cached_character=255;
    static bool valid;
    unsigned frame=v->pet_frame<F75_COMPANION_FRAMES?v->pet_frame:0;
    unsigned character=v->pet_character<F75_COMPANION_COUNT?v->pet_character:3;
    if(cached_frame!=frame||cached_character!=character){
        valid=f75_sprite_decode(f75_companion_streams[character][frame],f75_companion_lengths[character][frame],sprite,sizeof(sprite),6400);
        cached_frame=(uint8_t)frame;cached_character=(uint8_t)character;
    }
    if(!valid)return;
    int bob=v->pet_bob< -2?-2:v->pet_bob>2?2:v->pet_bob;
    int top=(int)t->y-24-bob,bottom=(int)t->y+t->rows-24-bob;
    if(top<0)top=0;
    if(bottom>80)bottom=80;
    for(int y=top;y<bottom;y++){
        uint16_t *out=t->pixels+(24+y+bob-t->y)*128+24;
        for(int x=0;x<80;x++){uint16_t color=f75_companion_palette[character][f75_sprite_index(sprite,(size_t)y*80+x)];if(color)out[x]=color;}
    }
    for(unsigned i=0;v->pet_effect&&i<8;i++){
        int x=i%2?108+(int)(i%3)*4:8+(int)(i%3)*4;
        int y=32+(int)((i*17+v->pet_phase*3)%60);
        if(v->pet_effect==1){rect(t,x-2,y,5,1,accent);rect(t,x,y-2,1,5,accent);}
        if(v->pet_effect==2){rect(t,x,y,2,2,0xf2b6);rect(t,x+3,y,2,2,0xf2b6);rect(t,x,y+2,5,1,0xf2b6);rect(t,x+1,y+3,3,1,0xf2b6);dot(t,x+2,y+4,0xf2b6);}
        if(v->pet_effect==3)rect(t,x,y,i%2?2:1,i%2?1:3,i%3?0xf632:0xb55f);
        if(v->pet_effect==4)rect(t,x-3,y,6,1,accent);
    }
}
static void spring(int32_t *position,int32_t *velocity,int32_t target,bool fast){
    *velocity=fast?(*velocity+(target-*position)/3)/2:(*velocity+(target-*position)/5)*3/5;
    *position+=*velocity;
    if(magnitude(target-*position)<32&&magnitude(*velocity)<24){*position=target;*velocity=0;}
}
void f75_motion_update(f75_motion *m,uint16_t context,uint8_t selected,int direction,uint32_t now,bool quiet){
    if(selected>4)selected=0;
    int32_t target=(int32_t)selected*15*256;
    if(!(m->flags&1)||quiet){
        m->selection=target;m->velocity=m->slide=m->slide_velocity=0;m->last_step=m->last_input=now;
        m->context=context;m->selected=selected;m->flags=1;return;
    }
    /* Advance the old target first, preserving position and velocity on reversal. */
    uint32_t elapsed=now-m->last_step;
    if(elapsed>512){m->selection=(int32_t)m->selected*15*256;m->velocity=m->slide=m->slide_velocity=0;m->last_step=now;}
    else while((uint32_t)(now-m->last_step)>=16){
        spring(&m->selection,&m->velocity,(int32_t)m->selected*15*256,(m->flags&2)!=0);
        spring(&m->slide,&m->slide_velocity,0,(m->flags&2)!=0);m->last_step+=16;
    }
    if(context!=m->context||selected!=m->selected){
        bool fast=(uint32_t)(now-m->last_input)<85;m->flags=(uint8_t)(1|(fast?2:0));m->last_input=now;
        if(context!=m->context){m->selection=target;m->velocity=0;m->slide=(direction<0?-12:12)*256;m->slide_velocity=0;}
        m->context=context;m->selected=selected;
    }
}
bool f75_motion_active(const f75_motion *m){return m->selection!=(int32_t)m->selected*15*256||m->velocity||m->slide||m->slide_velocity;}
void f75_motion_nudge(f75_motion *m,int direction,uint32_t now){
    if(!(m->flags&1))return;
    f75_motion_update(m,m->context,m->selected,direction,now,false);
    m->last_input=now;
    m->selection+=(direction<0?-2:2)*256;
    if(m->selection< -3*256)m->selection= -3*256;
    if(m->selection>63*256)m->selection=63*256;
}
void f75_motion_apply(const f75_motion *m,f75_view *v){
    v->motion=true;int y=(int)((m->selection+128)/256);v->highlight_y=(int16_t)(y< -3?-3:y>63?63:y);
    v->content_x=(int16_t)(m->slide/256);
}
bool f75_render_tile(const f75_view *v,uint8_t y,uint8_t rows,uint16_t *pixels,size_t capacity){
    if(!v||!pixels||!rows||rows>F75_TILE_ROWS||y+rows>128||capacity<(size_t)rows*128)return false;
    uint16_t BG=v->light_mode?0xef7b:0x08a2,INK=v->light_mode?0x1125:0xe7bc;
    uint16_t ACCENT=v->light_mode?0x1ba8:0xaf5a,MUTED=v->light_mode?0x4aeb:0xadf6,LINE=v->light_mode?0xcdf4:0x29e6;
    if(v->custom_accent)ACCENT=readable_accent(v->accent,v->light_mode);
    if(v->alert_pulse)BG=v->light_mode?0xded6:0x2349;
    tile t={y,rows,pixels};for(unsigned i=0;i<(unsigned)rows*128;i++)pixels[i]=BG;
    if(v->home&&!v->timer){
        text(&t,v->status_left,7,7,7,1,ACCENT);
        int icon_x=11+text_width(v->status_left,7,1);
        os_icon(&t,v,icon_x,4,ACCENT);
        text(&t,v->status_right,7,121-text_width(v->status_right,7,1),7,1,INK);
    }else text(&t,v->title,19,8,7,1,ACCENT);
    bool companion=v->home&&!v->timer&&v->face==3;
    uint16_t ROSE=v->light_mode?0xa2af:0xe51b;
    if(companion){
        rect(&t,7,20,44,1,LINE);rect(&t,77,20,44,1,LINE);
        heart(&t,61,18,ROSE);
    }else rect(&t,7,20,114,1,LINE);
    if(v->timer){
        centered(&t,v->clock,5,42,3,INK);
        rect(&t,9,79,110,3,LINE);rect(&t,9,79,(int)(v->timer_progress>100?100:v->timer_progress)*110/100,3,ACCENT);
        centered(&t,v->host_label,18,92,1,MUTED);
    }else if(v->home&&v->face==3){
        sparkle(&t,15,48,LINE);sparkle(&t,112,77,LINE);
        rect(&t,10,101,108,1,0xe5d7);rect(&t,8,102,112,2,0xc494);rect(&t,10,104,108,1,0x9b91);
        desk_clock(&t,v,ROSE);
        pet_sprite(&t,v,ACCENT);char rate[]="000 WPM";unsigned wpm=v->pet_wpm>999?999:v->pet_wpm;
        rate[0]=wpm>=100?(char)('0'+wpm/100):' ';rate[1]=wpm>=10?(char)('0'+wpm/10%10):' ';rate[2]=(char)('0'+wpm%10);
        const char *pace=rate+(wpm>=100?0:wpm>=10?1:2);
        text(&t,pace,7,6,105,0,MUTED);static const char *moods[]={"Idle","Typing","Flow","Zoom!","Sleepy","Sip","Stretch","Groove","Yay!"};
        const char *mood=moods[v->pet_mode<9?v->pet_mode:0];
        text(&t,mood,6,121-text_width(mood,6,0),105,0,ACCENT);
    }else if(v->home){
        centered(&t,v->clock,5,34,3,INK);centered(&t,v->host_label,18,65,1,MUTED);
        static const int8_t wave[]={0,1,2,3,3,3,2,1,0,-1,-2,-3,-3,-3,-2,-1};
        if(v->face!=1)for(unsigned i=0;i<13;i++){int yy=v->face==2?80+(int)((i*13)%11):84+wave[(v->animation_phase+i)&15];rect(&t,8+(int)i*9,yy,i%3?1:2,i%3?1:2,i%3?LINE:ACCENT);}
        text(&t,v->os,3,7,99,1,ACCENT);text(&t,v->caps_swap?(v->os[0]=='M'?"Caps: Cmd":"Caps: Ctrl"):"Caps normal",12,43,99,1,MUTED);
    }else{
        int x=v->motion?v->content_x:0;
        int highlight=v->motion?v->highlight_y:(int)v->selected*15;
        if(v->selected<5){
            soft_rect(&t,5+x,29+highlight,118,13,v->editing?LINE:ACCENT);
            if(v->editing){rect(&t,5+x,32+highlight,2,7,ACCENT);rect(&t,121+x,32+highlight,2,7,ACCENT);}
        }
        for(unsigned i=0;i<5;i++){
            bool covered=v->selected<5&&magnitude((int32_t)i*15-highlight)<7;
            text(&t,v->rows[i],19,9+x,30+(int)i*15,1,covered&&!v->editing?BG:INK);
        }
    }
    centered(&t,v->footer,20,117,0,MUTED);return true;
}
