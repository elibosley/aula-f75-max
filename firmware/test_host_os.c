#include "f75_core.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 f75_state s;f75_init(&s,NULL,0);f75_switch_host(&s,1,0);s.config.os[1]=F75_WINDOWS;uint32_t transaction=s.transaction,epoch=s.release_epoch;
 assert(!f75_host_os_hint(&s,2,F75_MAC,transaction,true));
 assert(!f75_host_os_hint(&s,1,F75_MAC,transaction-1,true));
 assert(!f75_host_os_hint(&s,1,F75_MAC,transaction,false));
 assert(s.config.os[1]==F75_WINDOWS&&s.release_epoch==epoch);
 assert(f75_host_os_hint(&s,1,F75_MAC,transaction,true)&&s.config.os[1]==F75_MAC&&s.release_epoch==epoch+1);
 assert(f75_map_usage(&s,0x39)==0xe3&&f75_map_usage(&s,0xe0)==0x39&&f75_map_usage(&s,0xe2)==0xe3);
 f75_set_os(&s,F75_WINDOWS);epoch=s.release_epoch;
 assert(!f75_host_os_hint(&s,1,F75_MAC,transaction,true)&&s.config.os[1]==F75_WINDOWS&&s.release_epoch==epoch);
 s.config.os_auto_mask|=2;f75_pair_request(&s,1,10);assert(!f75_host_os_hint(&s,1,F75_MAC,s.transaction,true));
 f75_pair_cancel(&s);assert(!f75_host_os_hint(&s,1,F75_MAC,transaction,true));
 puts("Host OS evidence: route, transaction, link, manual override and pairing guards; Caps/Ctrl invariant passed.");
}
