#ifndef F75_USB_LINK_H
#define F75_USB_LINK_H
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    uint32_t changed_at;
    uint16_t frame;
    bool configured, progressed;
} f75_usb_link;
/* Configuration alone can survive cable removal on a self-powered board.
 * Only a recently advancing host SOF counter proves a live USB data link. */
bool f75_usb_link_observe(f75_usb_link *link,bool configured,uint16_t frame,uint32_t now);
#endif
