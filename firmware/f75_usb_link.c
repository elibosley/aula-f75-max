#include "f75_usb_link.h"
bool f75_usb_link_observe(f75_usb_link *link,bool configured,uint16_t frame,uint32_t now){
    if(!configured){link->configured=false;link->progressed=false;return false;}
    frame&=2047u;
    if(!link->configured){
        link->configured=true;link->progressed=false;link->frame=frame;link->changed_at=now;
        return false;
    }
    if(frame!=link->frame){link->frame=frame;link->changed_at=now;link->progressed=true;}
    if((uint32_t)(now-link->changed_at)>=100u)link->progressed=false;
    return link->progressed;
}
