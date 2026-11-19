#include "f75_usb_link.h"
#include <assert.h>
#include <stdio.h>
int main(void){
    f75_usb_link link={0};
    assert(!f75_usb_link_observe(&link,false,0,0));
    assert(!f75_usb_link_observe(&link,true,120,1)); /* A cached frame is not enough. */
    assert(f75_usb_link_observe(&link,true,121,2));
    assert(f75_usb_link_observe(&link,true,121,101));
    assert(!f75_usb_link_observe(&link,true,121,102)); /* Driver still says configured. */
    assert(!f75_usb_link_observe(&link,true,121,100000));
    assert(!f75_usb_link_observe(&link,true,121,2)); /* No false revival after time wrap. */
    assert(f75_usb_link_observe(&link,true,122,3)); /* New SOF restores the link. */
    assert(!f75_usb_link_observe(&link,false,122,4));
    assert(!f75_usb_link_observe(&link,true,2047,0xfffffff0u));
    assert(f75_usb_link_observe(&link,true,0,0xfffffff1u)); /* 11-bit SOF wrap. */
    assert(f75_usb_link_observe(&link,true,0,0x40u)); /* Millisecond wrap. */
    assert(!f75_usb_link_observe(&link,true,0,0x55u));
    assert(f75_usb_link_observe(&link,true,1,0x56u));
    puts("USB link checks passed: cached configuration, SOF loss/resume, reset and counter wraps.");
}
