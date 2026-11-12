// SPDX-License-Identifier: MIT
// A permission-gated, enrolled-device-only Bluetooth output probe.
// Configuration replies use only the Constant padding byte. Raw key fields
// are discarded. Quiet probes count events without recording keys or text.
#import <Foundation/Foundation.h>
#import <IOKit/hid/IOHIDManager.h>
#import <IOKit/hidsystem/IOHIDLib.h>
#import <CommonCrypto/CommonDigest.h>
#import <CoreGraphics/CoreGraphics.h>
#import <AppKit/NSEvent.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static BOOL capturingReports;
static void stop(int sig) { interrupted = sig; }
static id property(IOHIDDeviceRef device, NSString *key) {
    return CFBridgingRelease(IORegistryEntryCreateCFProperty(IOHIDDeviceGetService(device),
        (__bridge CFStringRef)key, kCFAllocatorDefault, 0));
}
static NSString *data_hash(NSData *data) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *result = [NSMutableString string];
    for (unsigned i = 0; i < sizeof(digest); ++i) [result appendFormat:@"%02x", digest[i]];
    return result;
}
static NSString *identity(NSString *serial) {
    if (![serial isKindOfClass:[NSString class]] || !serial.length) return nil;
    return data_hash([serial dataUsingEncoding:NSUTF8StringEncoding]);
}
static NSString *status(IOReturn result) { return [NSString stringWithFormat:@"0x%08x", result]; }

static IOReturn read_leds(IOHIDDeviceRef device, uint8_t *flags) {
    CFArrayRef elements = IOHIDDeviceCopyMatchingElements(device, (__bridge CFDictionaryRef)
        @{@"UsagePage": @8, @"Type": @(kIOHIDElementTypeOutput)}, 0);
    if (!elements) return kIOReturnUnsupported;
    uint8_t known = 0;
    IOReturn result = kIOReturnSuccess;
    *flags = 0;
    for (CFIndex i = 0; i < CFArrayGetCount(elements); ++i) {
        IOHIDElementRef element = (IOHIDElementRef)CFArrayGetValueAtIndex(elements, i);
        uint32_t usage = IOHIDElementGetUsage(element);
        if (usage < 1 || usage > 3 || IOHIDElementGetReportID(element) != 2) continue;
        IOHIDValueRef value = NULL;
        uint8_t bit = 1u << (usage - 1);
        if (known & bit) { result = kIOReturnUnsupported; break; }
        result = IOHIDDeviceGetValue(device, element, &value);
        if (result != kIOReturnSuccess) break;
        if (!value) { result = kIOReturnUnsupported; break; }
        CFIndex state = IOHIDValueGetIntegerValue(value);
        if (state < 0 || state > 1) { result = kIOReturnUnsupported; break; }
        if (state) *flags |= bit;
        known |= bit;
    }
    CFRelease(elements);
    return result == kIOReturnSuccess && known != 7 ? kIOReturnUnsupported : result;
}

static IOReturn write_symbol(IOHIDDeviceRef device, uint8_t flags, uint8_t symbol) {
    const uint8_t report[] = {2, flags | (symbol << 5)};
    IOReturn result=IOHIDDeviceSetReport(device, kIOHIDReportTypeOutput, 2, report, sizeof(report));
    if(capturingReports) CFRunLoopRunInMode(kCFRunLoopDefaultMode,0,true);
    return result;
}

static BOOL display_preflight(IOHIDDeviceRef device, uint8_t *flags, NSMutableDictionary *receipt) {
    NSData *descriptor = property(device, @"ReportDescriptor");
    if (![descriptor isKindOfClass:[NSData class]] || descriptor.length != 361 ||
        ![data_hash(descriptor) isEqual:@"34af33fd6776d8cdd456c5d2bd51d40025dd3141564a91333f35b0265e2db584"]) {
        receipt[@"display_transport"] = @"Report descriptor mismatch";
        return NO;
    }
    IOReturn result = read_leds(device, flags);
    receipt[@"display_led_read_status"] = status(result);
    return result == kIOReturnSuccess && !interrupted;
}

static BOOL send_display(IOHIDDeviceRef device, const uint8_t *data, size_t length,
                         uint8_t flags, NSMutableDictionary *receipt) {
    uint32_t checksum = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        checksum ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            checksum = (checksum >> 1) ^ ((checksum & 1u) ? 0xedb88320u : 0u);
        }
    }
    checksum = ~checksum;
    unsigned sent = 0;
    uint8_t previous = 7;
    IOReturn result = write_symbol(device, flags, previous);
    for (size_t i = 0; result == kIOReturnSuccess && !interrupted && i < length + 4; ++i) {
        uint8_t byte = i < length ? data[i] : (uint8_t)(checksum >> (8 * (i - length)));
        for (int shift = 6; shift >= 0 && result == kIOReturnSuccess && !interrupted; shift -= 2) {
            uint8_t digit = (byte >> shift) & 3;
            previous = previous == 7 ? digit + 1 : (previous + digit) % 6 + 1;
            result = write_symbol(device, flags, previous);
            if (result == kIOReturnSuccess) ++sent;
        }
    }
    // Leave time for the last radio report before restoring normal LED output.
    if(capturingReports) CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.1,false);
    else usleep(100000);
    uint8_t latest_flags;
    if (read_leds(device, &latest_flags) == kIOReturnSuccess) flags = latest_flags;
    IOReturn restored = write_symbol(device, flags, 0);
    receipt[@"display_send_status"] = status(result);
    receipt[@"display_symbols_sent"] = @(sent);
    receipt[@"display_led_restore_status"] = status(restored);
    return result == kIOReturnSuccess && restored == kIOReturnSuccess && sent == 4 * (length + 4);
}

typedef struct {
    uint8_t buffer[64], values[1024];
    unsigned head, tail, received, lengths, active_key_reports, modifier_reports, fn_reports;
    uint32_t report_ids;
    BOOL overflow, probe_fields_zero, probe_seen;
    uint8_t expected_probe;
} PaddingCapture;
static void padding_report(void *context, IOReturn result, void *sender,
    IOHIDReportType type, uint32_t reportID, uint8_t *report, CFIndex length) {
    (void)sender;
    PaddingCapture *capture=context;
    if(result!=kIOReturnSuccess || type!=kIOHIDReportTypeInput) return;
    if(reportID<32) capture->report_ids|=1u<<reportID;
    if(reportID!=2) return;
    const uint8_t *data=NULL;
    if(length==8) data=report;
    else if(length==9 && report[0]==2) data=report+1;
    else return;
    capture->lengths|=1u<<(unsigned)length;
    BOOL keys=NO;
    for(unsigned i=2;i<7;++i)if(data[i])keys=YES;
    if(keys)++capture->active_key_reports;
    if(data[0])++capture->modifier_reports;
    if(data[7])++capture->fn_reports;
    uint8_t value=data[1];
    if(value==capture->expected_probe) {
        capture->probe_seen=YES;
        for(unsigned i=0;i<8;++i) if(i!=1 && data[i]) capture->probe_fields_zero=NO;
    }
    unsigned next=(capture->head+1u)&1023u;
    if(next==capture->tail) capture->overflow=YES;
    else {capture->values[capture->head]=value;capture->head=next;}
    ++capture->received;
}
static void padding_start(IOHIDDeviceRef device, PaddingCapture *capture, NSMutableDictionary *receipt) {
    capture->probe_fields_zero=YES;
    IOHIDDeviceScheduleWithRunLoop(device,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    IOHIDDeviceRegisterInputReportCallback(device,capture->buffer,sizeof(capture->buffer),padding_report,capture);
    capturingReports=YES;
    receipt[@"input_callbacks_registered"]=@YES;
    receipt[@"retains_key_codes"]=@NO;
    receipt[@"retains_typed_text"]=@NO;
    receipt[@"reply_carrier"]=@"report_2_constant_byte_1";
}
static int padding_next(PaddingCapture *capture) {
    if(capture->head==capture->tail) CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.025,true);
    if(capture->head==capture->tail) return -1;
    int value=capture->values[capture->tail];capture->tail=(capture->tail+1u)&1023u;return value;
}
static void padding_stop(IOHIDDeviceRef device, PaddingCapture *capture, NSMutableDictionary *receipt) {
    IOHIDDeviceRegisterInputReportCallback(device,capture->buffer,sizeof(capture->buffer),NULL,NULL);
    IOHIDDeviceUnscheduleFromRunLoop(device,CFRunLoopGetCurrent(),kCFRunLoopDefaultMode);
    capturingReports=NO;
    receipt[@"raw_report_ids_seen"]=@(capture->report_ids);
    receipt[@"raw_report_lengths_seen"]=@(capture->lengths);
    receipt[@"capture_overflow"]=@(capture->overflow);
    receipt[@"target_reports_received"]=@(capture->received);
    receipt[@"target_active_key_reports"]=@(capture->active_key_reports);
    receipt[@"target_modifier_reports"]=@(capture->modifier_reports);
    receipt[@"target_fn_reports"]=@(capture->fn_reports);
    memset(capture->buffer,0,sizeof(capture->buffer));
}
typedef struct { unsigned down,up,flags,system,subtypes[256],zero_mouse_states,nonzero_mouse_states,zero_source_keys,nonzero_source_keys,source_pids[16],source_count; BOOL disabled,conversion_failed; } KeyEventCounts;
static CGEventRef count_key_event(CGEventTapProxy proxy,CGEventType type,CGEventRef event,void *context) {
    (void)proxy;KeyEventCounts *counts=context;
    if(type==kCGEventKeyDown||type==kCGEventKeyUp||type==kCGEventFlagsChanged){
        int64_t pid=CGEventGetIntegerValueField(event,kCGEventSourceUnixProcessID);
        if(pid==0)++counts->zero_source_keys;
        else{
            ++counts->nonzero_source_keys;
            BOOL known=NO;
            for(unsigned i=0;i<counts->source_count;++i)if(counts->source_pids[i]==(unsigned)pid)known=YES;
            if(!known&&counts->source_count<16)counts->source_pids[counts->source_count++]=(unsigned)pid;
        }
    }
    if(type==kCGEventKeyDown)++counts->down;
    else if(type==kCGEventKeyUp)++counts->up;
    else if(type==kCGEventFlagsChanged)++counts->flags;
    else if(type==(CGEventType)NX_SYSDEFINED){
        ++counts->system;
        NSEvent *native=[NSEvent eventWithCGEvent:event];
        if(!native)counts->conversion_failed=YES;
        else if(native.subtype>=0 && native.subtype<256){
            ++counts->subtypes[native.subtype];
            if(native.subtype==NX_SUBTYPE_AUX_MOUSE_BUTTONS){
                if(native.data1==0)++counts->zero_mouse_states;else ++counts->nonzero_mouse_states;
            }
        }
    }
    else if(type==kCGEventTapDisabledByTimeout || type==kCGEventTapDisabledByUserInput)counts->disabled=YES;
    return event;
}
static unsigned system_key_events(const KeyEventCounts *counts) {
    // These SDK-defined subtypes are pointer state or parameter notices,
    // not keyboard/media keys. Keep their totals in the receipt separately.
    unsigned nonkeys=counts->subtypes[NX_SUBTYPE_AUX_MOUSE_BUTTONS]+
        counts->subtypes[NX_SUBTYPE_MOUSE_TOUCH]+counts->subtypes[NX_SUBTYPE_HIDPARAMETER_MODIFIED];
    return counts->system-nonkeys+(counts->conversion_failed?1u:0u);
}
static BOOL test_reply(IOHIDDeviceRef device, const uint8_t *data, uint8_t flags,
                       NSMutableDictionary *receipt) {
    const uint8_t probes[16]={0x80,0x40,0x20,0x10,8,4,2,1,0x55,0xaa,0xfe,0xff,0x7f,0x81,0x5a,0xa5};
    PaddingCapture capture={0};capture.expected_probe=data?probes[data[1]]:0x80;
    KeyEventCounts counts={0};
    CFMachPortRef tap=CGEventTapCreate(kCGSessionEventTap,kCGHeadInsertEventTap,kCGEventTapOptionListenOnly,
        CGEventMaskBit(kCGEventKeyDown)|CGEventMaskBit(kCGEventKeyUp)|CGEventMaskBit(kCGEventFlagsChanged)|CGEventMaskBit((CGEventType)NX_SYSDEFINED),
        count_key_event,&counts);
    receipt[@"quiet_probe_available"]=@(tap!=NULL);
    receipt[@"counts_key_events"]=@YES;
    if(!tap) return NO;
    CFRunLoopSourceRef source=CFMachPortCreateRunLoopSource(kCFAllocatorDefault,tap,0);
    if(!source){CFRelease(tap);return NO;}
    CFRunLoopAddSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);CGEventTapEnable(tap,true);
    CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.15,false);
    BOOL quiet=!(counts.down||counts.up||counts.flags||system_key_events(&counts)||counts.disabled),matched=NO;
    receipt[@"baseline_key_down_events"]=@(counts.down);
    receipt[@"baseline_key_up_events"]=@(counts.up);
    receipt[@"baseline_modifier_events"]=@(counts.flags);
    BOOL transmitted=NO;
    padding_start(device,&capture,receipt);
    if(!data)CFRunLoopRunInMode(kCFRunLoopDefaultMode,5.0,false);
    else if(quiet && (transmitted=YES) && send_display(device,data,3,flags,receipt)) {
        NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:2];
        while(!interrupted && deadline.timeIntervalSinceNow>0) {
            int value=padding_next(&capture);
            if(value==capture.expected_probe){matched=YES;break;}
        }
        CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.2,false);
    }
    padding_stop(device,&capture,receipt);
    CFRunLoopRemoveSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);CFMachPortInvalidate(tap);
    CFRelease(source);CFRelease(tap);
    receipt[@"probe_padding_value"]=@(capture.expected_probe);
    receipt[@"probe_nonpadding_fields_zero"]=@(capture.probe_fields_zero);
    receipt[@"probe_key_down_events"]=@(counts.down);receipt[@"probe_key_up_events"]=@(counts.up);
    receipt[@"probe_modifier_events"]=@(counts.flags);receipt[@"probe_event_monitor_disabled"]=@(counts.disabled);
    receipt[@"probe_system_key_events"]=@(system_key_events(&counts));
    receipt[@"system_events_total"]=@(counts.system);
    receipt[@"aux_mouse_zero_states"]=@(counts.zero_mouse_states);
    receipt[@"aux_mouse_nonzero_states"]=@(counts.nonzero_mouse_states);
    NSMutableDictionary *subtypes=[NSMutableDictionary dictionary];
    for(unsigned i=0;i<256;++i)if(counts.subtypes[i])subtypes[[NSString stringWithFormat:@"%u",i]]=@(counts.subtypes[i]);
    receipt[@"system_event_subtypes"]=subtypes;
    receipt[@"system_event_conversion_failed"]=@(counts.conversion_failed);
    receipt[@"probe_transmitted"]=@(transmitted);
    receipt[@"key_events_source_pid_zero"]=@(counts.zero_source_keys);
    receipt[@"key_events_source_pid_nonzero"]=@(counts.nonzero_source_keys);
    NSMutableArray *sources=[NSMutableArray array];
    for(unsigned i=0;i<counts.source_count;++i)[sources addObject:@(counts.source_pids[i])];
    receipt[@"key_event_source_pids"]=sources;
    BOOL safe=matched && capture.probe_fields_zero && !capture.active_key_reports && !capture.modifier_reports && !capture.fn_reports && !capture.overflow && !counts.down && !counts.up && !counts.flags && !system_key_events(&counts) && !counts.disabled;
    receipt[@"padding_value_forwarded"]=@(matched);
    receipt[@"reply_challenge_matched"]=@(safe);
    return data?safe:YES;
}

static uint32_t packet_crc(const uint8_t *data, size_t length) {
    uint32_t value = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        value ^= data[i];
        for (unsigned j = 0; j < 8; ++j)
            value = (value >> 1) ^ ((value & 1u) ? 0xedb88320u : 0u);
    }
    return ~value;
}

static BOOL fast_qualified(IOHIDDeviceRef device) {
    NSString *root=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"F75ProjectRoot"];
    NSData *data=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@".runtime/ble-padding-qualified.json"]];
    NSDictionary *q=data?[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL]:nil;
    return [q isKindOfClass:[NSDictionary class]] && [q[@"fast_settings_version"] isEqual:@1] &&
        [q[@"fast_capability_verified"] isEqual:@YES] && [q[@"protocol"] isEqual:@3] &&
        [q[@"probe_count"] isEqual:@16] && [q[@"all_bit_patterns_passed"] isEqual:@YES] &&
        [q[@"key_events_observed"] isEqual:@0] &&
        [q[@"descriptor_sha256"] isEqual:@"34af33fd6776d8cdd456c5d2bd51d40025dd3141564a91333f35b0265e2db584"] &&
        [q[@"serial_sha256"] isEqual:identity(property(device,@"SerialNumber"))];
}

static BOOL send_fast(IOHIDDeviceRef device,const uint8_t *data,size_t length,uint8_t flags,NSMutableDictionary *receipt) {
    CFAbsoluteTime started=CFAbsoluteTimeGetCurrent();
    uint32_t checksum=packet_crc(data,length);unsigned sent=0;uint8_t previous=27;
    uint8_t report[2]={2,(uint8_t)(flags|(previous<<3))};
    IOReturn result=write_symbol(device,flags,0);
    if(result==kIOReturnSuccess)result=IOHIDDeviceSetReport(device,kIOHIDReportTypeOutput,2,report,sizeof(report));
    for(size_t at=0;result==kIOReturnSuccess&&!interrupted&&at<length+4;++at){
        uint8_t byte=at<length?data[at]:(uint8_t)(checksum>>(8*(at-length)));
        for(int shift=4;shift>=0&&result==kIOReturnSuccess&&!interrupted;shift-=4){
            uint8_t digit=(byte>>shift)&15;
            previous=previous==27?digit+1:(previous+digit)%26+1;
            report[1]=(uint8_t)(flags|(previous<<3));
            result=IOHIDDeviceSetReport(device,kIOHIDReportTypeOutput,2,report,sizeof(report));
            CFRunLoopRunInMode(kCFRunLoopDefaultMode,0,true);
            if(result==kIOReturnSuccess)++sent;
        }
    }
    CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.02,false);
    uint8_t latest;if(read_leds(device,&latest)==kIOReturnSuccess)flags=latest;
    IOReturn restored=write_symbol(device,flags,0);
    receipt[@"fast_request_seconds"]=@(CFAbsoluteTimeGetCurrent()-started);
    receipt[@"display_send_status"]=status(result);receipt[@"display_led_restore_status"]=status(restored);
    receipt[@"display_symbols_sent"]=@(sent);receipt[@"output_bits_per_symbol"]=@4;
    return result==kIOReturnSuccess&&restored==kIOReturnSuccess&&sent==2*(length+4);
}

static BOOL settings_request(IOHIDDeviceRef device, const uint8_t *data, size_t length,
                             uint8_t flags, NSMutableDictionary *receipt) {
    BOOL fast=data[0]==5;
    NSString *root=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"F75ProjectRoot"];
    NSData *qualificationData=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@".runtime/ble-padding-qualified.json"]];
    NSDictionary *qualification=qualificationData?[NSJSONSerialization JSONObjectWithData:qualificationData options:0 error:NULL]:nil;
    NSString *serial=identity(property(device,@"SerialNumber"));
    BOOL qualified=[qualification isKindOfClass:[NSDictionary class]] &&
        [qualification[@"protocol"] isEqual:@3] &&
        [qualification[@"probe_count"] isEqual:@16] &&
        [qualification[@"all_bit_patterns_passed"] isEqual:@YES] &&
        [qualification[@"key_events_observed"] isEqual:@0] &&
        [qualification[@"descriptor_sha256"] isEqual:@"34af33fd6776d8cdd456c5d2bd51d40025dd3141564a91333f35b0265e2db584"] &&
        serial && [qualification[@"serial_sha256"] isEqual:serial];
    receipt[@"padding_transport_qualified"]=@(qualified);
    if(!qualified || (fast&&!fast_qualified(device))) {
        receipt[@"settings_reply_verified"]=@NO;
        receipt[@"settings_reply_failure"]=@"Constant padding transport not qualified";
        return NO;
    }
    // Count OS keyboard events during this RPC without retaining key codes.
    // Normal use can include deliberate typing; quiet hardware tests inspect
    // these counters independently of the verified data response.
    KeyEventCounts eventCounts={0};
    CFMachPortRef eventTap=CGEventTapCreate(kCGSessionEventTap,kCGHeadInsertEventTap,kCGEventTapOptionListenOnly,
        CGEventMaskBit(kCGEventKeyDown)|CGEventMaskBit(kCGEventKeyUp)|CGEventMaskBit(kCGEventFlagsChanged)|CGEventMaskBit((CGEventType)NX_SYSDEFINED),
        count_key_event,&eventCounts);
    CFRunLoopSourceRef eventSource=eventTap?CFMachPortCreateRunLoopSource(kCFAllocatorDefault,eventTap,0):NULL;
    if(!eventTap||!eventSource){
        if(eventTap)CFRelease(eventTap);
        receipt[@"settings_reply_failure"]=@"Keyboard event monitor unavailable";
        receipt[@"settings_reply_verified"]=@NO;
        return NO;
    }
    CFRunLoopAddSource(CFRunLoopGetCurrent(),eventSource,kCFRunLoopDefaultMode);
    CGEventTapEnable(eventTap,true);
    PaddingCapture capture={0};
    BOOL verified = NO;
    NSString *failure = @"Reply timed out";
    unsigned received = 0, completedBytes = 0, duplicates = 0;
    padding_start(device,&capture,receipt);
    {
        if (fast?send_fast(device,data,length,flags,receipt):send_display(device, data, length, flags, receipt)) {
            failure = @"Reply timed out";
            uint8_t response[271] = {0};
            unsigned groups = 0, bits = 0, bytes = 0, expected = 0;
            BOOL started = NO;
            CFIndex previous = -1;
            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:12];
            while (!interrupted && deadline.timeIntervalSinceNow > 0) {
                int raw=padding_next(&capture);
                if(raw<0) continue;
                ++received;
                if (!started) { if (raw == 255) { started = YES; previous = raw; } continue; }
                if (raw == previous) { ++duplicates; continue; }
                previous = raw;
                if (((raw >> 7) & 1) != (groups & 1u)) { failure = @"Reply parity mismatch"; break; }
                ++groups;
                for (unsigned bit = 0; bit < 7 && bytes < sizeof(response); ++bit) {
                    response[bytes] |= ((raw >> bit) & 1u) << bits;
                    if (++bits != 8) continue;
                    bits = 0; ++bytes;
                    if (bytes == 11) {
                        unsigned payload = response[9] | ((unsigned)response[10] << 8);
                        if (payload > 256) break;
                        expected = 15 + payload;
                    }
                    if (expected && bytes == expected) break;
                }
                completedBytes = bytes;
                if (bytes >= 11 && !expected) { failure = @"Reply length invalid"; break; }
                if (!expected || bytes < expected) continue;
                uint32_t checksum = 0;
                for (unsigned i = 0; i < 4; ++i) checksum |= (uint32_t)response[expected - 4 + i] << (i * 8);
                verified = !memcmp(response, data + 3, 4) && response[4] == data[fast?1:11] &&
                    response[7] == data[fast?7:12] && response[8] == data[fast?8:13] &&
                    packet_crc(response, expected - 4) == checksum;
                failure = verified ? @"" : @"Reply CRC or identity mismatch";
                if (verified) {
                    NSMutableString *hex = [NSMutableString string];
                    for (unsigned i = 0; i < expected; ++i) [hex appendFormat:@"%02x", response[i]];
                    receipt[@"settings_response_hex"] = hex;
                }
                break;
            }
        }
        padding_stop(device,&capture,receipt);
    }
    CFRunLoopRunInMode(kCFRunLoopDefaultMode,0.1,false);
    CFRunLoopRemoveSource(CFRunLoopGetCurrent(),eventSource,kCFRunLoopDefaultMode);
    CFMachPortInvalidate(eventTap);CFRelease(eventSource);CFRelease(eventTap);
    receipt[@"settings_key_down_events"]=@(eventCounts.down);
    receipt[@"settings_key_up_events"]=@(eventCounts.up);
    receipt[@"settings_modifier_events"]=@(eventCounts.flags);
    receipt[@"settings_system_key_events"]=@(system_key_events(&eventCounts));
    receipt[@"settings_event_monitor_disabled"]=@(eventCounts.disabled);
    receipt[@"settings_event_monitor_available"]=@YES;
    receipt[@"settings_key_events_source_pid_zero"]=@(eventCounts.zero_source_keys);
    receipt[@"settings_key_events_source_pid_nonzero"]=@(eventCounts.nonzero_source_keys);
    NSMutableArray *sources=[NSMutableArray array];
    for(unsigned i=0;i<eventCounts.source_count;++i)[sources addObject:@(eventCounts.source_pids[i])];
    receipt[@"settings_key_event_source_pids"]=sources;
    if(capture.overflow){verified=NO;failure=@"Padding capture overflow";}
    if(eventCounts.disabled){verified=NO;failure=@"Keyboard event monitor disabled";}
    receipt[@"settings_reply_verified"] = @(verified);
    receipt[@"settings_reply_failure"] = failure;
    receipt[@"settings_reply_symbols_received"] = @(received);
    receipt[@"settings_reply_bytes_received"] = @(completedBytes);
    receipt[@"settings_reply_duplicates_ignored"] = @(duplicates);
    return verified;
}

static int hex_digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

int main(int argc, const char **argv) {
 @autoreleasepool {
    BOOL request = NO, openCheck = NO, ledTest = NO;
    NSString *expectedBoard = nil;
    BOOL displayInfo = NO, displaySent = NO, observePadding = NO;
    uint8_t display[67] = {0};
    size_t displayLength = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--board") && i + 1 < argc) {
            expectedBoard = [NSString stringWithUTF8String:argv[++i]];
            NSCharacterSet *hex = [NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"];
            if (expectedBoard.length != 64 || [expectedBoard rangeOfCharacterFromSet:hex.invertedSet].location != NSNotFound) return 2;
        }
        else if (!strcmp(argv[i], "--check")) continue;
        else if (!strcmp(argv[i], "--request-access")) request = YES;
        else if (!strcmp(argv[i], "--open-check")) openCheck = YES;
        else if (!strcmp(argv[i], "--led-test")) ledTest = openCheck = YES;
        else if (!strcmp(argv[i], "--status-info")) displayInfo = openCheck = YES;
        else if (!strcmp(argv[i], "--observe-padding")) observePadding = openCheck = YES;
        else if (!strcmp(argv[i], "--fast-settings-request") && !displayLength) {
            char hex[131];if(!fgets(hex,sizeof(hex),stdin))return 2;
            size_t size=strcspn(hex,"\r\n");if(size<14||size>110||size%2)return 2;
            uint8_t raw[55]={0};
            for(size_t j=0;j<size;j+=2){int a=hex_digit(hex[j]),b=hex_digit(hex[j+1]);if(a<0||b<0)return 2;raw[j/2]=(a<<4)|b;}
            if(raw[4]!=9&&raw[4]!=10)return 2;
            display[0]=5;display[1]=raw[4];display[2]=(uint8_t)(size/2-1);
            memcpy(display+3,raw,4);memcpy(display+7,raw+5,size/2-5);
            displayLength=3+display[2];openCheck=YES;
        }
        else if (!strcmp(argv[i], "--settings-request") && !displayLength) {
            char hex[131];
            if (!fgets(hex, sizeof(hex), stdin)) return 2;
            size_t size = strcspn(hex, "\r\n");
            if (size < 26 || size > 128 || size % 2) return 2;
            for (size_t j = 0; j < size; j += 2) {
                int a = hex_digit(hex[j]), b = hex_digit(hex[j + 1]);
                if (a < 0 || b < 0) return 2;
                display[3 + j / 2] = (a << 4) | b;
            }
            display[0] = 4; display[1] = 1; display[2] = size / 2;
            displayLength = 3 + size / 2; openCheck = YES;
        }
        else if (!strcmp(argv[i], "--reply-test") && !displayLength && i + 1 < argc) {
            const char *number = argv[++i];
            char *end = NULL;
            long challenge = strtol(number, &end, 10);
            if (end == number || *end || challenge < 0 || challenge > 15) return 2;
            display[0] = 3;
            display[1] = (uint8_t)challenge;
            displayLength = 3;
            openCheck = YES;
        }
        else if (!strcmp(argv[i], "--clear-status") && !displayLength) {
            display[0] = 2;
            displayLength = 3;
            openCheck = YES;
        } else if (!strcmp(argv[i], "--status") && !displayLength && i + 2 < argc) {
            const char *text = argv[++i];
            size_t length = strlen(text);
            char *end = NULL;
            long seconds = strtol(argv[++i], &end, 10);
            if (!length || length > 20 || *end || seconds < 1 || seconds > 60) return 2;
            for (size_t j = 0; j < length; ++j) {
                if ((uint8_t)text[j] < 32 || (uint8_t)text[j] > 126) return 2;
            }
            display[0] = 1;
            display[1] = (uint8_t)seconds;
            display[2] = (uint8_t)length;
            memcpy(display + 3, text, length);
            displayLength = 3 + length;
            openCheck = YES;
        } else {
            fprintf(stderr, "Use --check, --request-access, --open-check, --led-test, --status-info, --status TEXT SECONDS, --clear-status, --observe-padding, --reply-test CHALLENGE, or --settings-request (hex on stdin)\n");
            return 2;
        }
    }
    if ((ledTest && (displayLength || displayInfo)) || (displayLength && displayInfo)) return 2;
    if(observePadding && (ledTest || displayLength || displayInfo))return 2;
    signal(SIGTERM, stop); signal(SIGINT, stop);
    NSString *root = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"F75ProjectRoot"];
    if (!root.length) { fprintf(stderr, "Launch the built app bundle\n"); return 2; }
    NSString *runtime = [root stringByAppendingPathComponent:@".runtime"];
    NSString *receipt = [runtime stringByAppendingPathComponent:@"mac-wireless-probe.json"];
    NSData *bindingData = [NSData dataWithContentsOfFile:[runtime stringByAppendingPathComponent:@"host-bindings.json"]];
    NSDictionary *bindings = bindingData ? [NSJSONSerialization JSONObjectWithData:bindingData options:0 error:NULL] : nil;
    if (![bindings isKindOfClass:[NSDictionary class]] || ![bindings[@"version"] isEqual:@1] ||
        ![bindings[@"boards"] isKindOfClass:[NSDictionary class]]) {
        fprintf(stderr, "Enroll this keyboard with the cabled helper first\n"); return 2;
    }
    IOHIDAccessType access = IOHIDCheckAccess(kIOHIDRequestTypeListenEvent);
    BOOL prompted = NO;
    if (request && access != kIOHIDAccessTypeGranted) {
        prompted = YES; IOHIDRequestAccess(kIOHIDRequestTypeListenEvent);
        access = IOHIDCheckAccess(kIOHIDRequestTypeListenEvent);
    }
    NSMutableDictionary *result = [@{
        @"version": @1, @"observed_at": [[NSISO8601DateFormatter new] stringFromDate:[NSDate date]],
        @"bundle_id": [[NSBundle mainBundle] bundleIdentifier],
        @"access": access == kIOHIDAccessTypeGranted ? @"granted" : access == kIOHIDAccessTypeDenied ? @"denied" : @"unknown",
        @"permission_requested": @(prompted), @"retains_key_codes": @NO, @"retains_typed_text": @NO,
        @"input_callbacks_registered": @NO, @"writes_flash": @NO,
        @"open_requested": @(openCheck), @"open_attempted": @NO, @"led_write_attempted": @NO
    } mutableCopy];
    if (display[0] == 4 || display[0] == 5) {
        BOOL save = display[0]==5?(display[1]==10&&display[7]==1&&display[8]==0):(displayLength == 21 && display[11] == 4 && display[20] == 1);
        result[@"settings_save_requested"] = @(save);
        result[@"writes_flash"] = @(save);
        result[@"writes_radio_flash"] = @NO;
    }
    IOHIDManagerRef manager = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
    IOHIDManagerSetDeviceMatching(manager, (__bridge CFDictionaryRef)@{@"VendorID": @0x05ac, @"ProductID": @0x024f});
    CFSetRef devices = IOHIDManagerCopyDevices(manager);
    NSMutableArray *matches = [NSMutableArray array];
    NSMutableArray *candidates = [NSMutableArray array];
    IOHIDDeviceRef target = NULL;
    if (devices) for (id object in (__bridge NSSet *)devices) {
        IOHIDDeviceRef device = (__bridge IOHIDDeviceRef)object;
        NSString *name = property(device, @"Product");
        if (![@[@"AULA F75Max-1", @"AULA F75Max-2", @"AULA F75Max-3"] containsObject:name]) continue;
        NSString *transport = property(device, @"Transport");
        BOOL keyboard = [property(device, @"PrimaryUsagePage") isEqual:@1] && [property(device, @"PrimaryUsage") isEqual:@6];
        [candidates addObject:@{@"product": name, @"transport": transport ?: @"unknown", @"keyboard_collection": @(keyboard)}];
        if (![@[@"Bluetooth", @"Bluetooth Low Energy"] containsObject:transport] || !keyboard) continue;
        NSString *slot = [name substringFromIndex:name.length - 1];
        NSString *serial = identity(property(device, @"SerialNumber"));
        unsigned owners = 0; NSString *ownerIdentity = nil;
        for (NSString *boardIdentity in bindings[@"boards"]) {
            id board = bindings[@"boards"][boardIdentity];
            if ([board isKindOfClass:[NSDictionary class]] && serial && [board[slot] isEqual:serial]) { ++owners; ownerIdentity = boardIdentity; }
        }
        [matches addObject:@{@"slot": @([slot intValue]), @"enrolled_owners": @(owners), @"board_identity": owners == 1 ? ownerIdentity : @""}];
        if (owners == 1 && (!expectedBoard || [ownerIdentity isEqual:expectedBoard])) { if (target) { result[@"ambiguous"] = @YES; } else target = device; }
    }
    result[@"candidate_metadata"] = candidates;
    result[@"local_wireless_devices"] = matches;
    result[@"fast_settings_version"]=@(target&&![result[@"ambiguous"] boolValue]&&fast_qualified(target)?1:0);
    if([result[@"fast_settings_version"] intValue]==1) {
        NSString *root=[[NSBundle mainBundle] objectForInfoDictionaryKey:@"F75ProjectRoot"];
        NSData *bytes=[NSData dataWithContentsOfFile:[root stringByAppendingPathComponent:@".runtime/ble-padding-qualified.json"]];
        NSDictionary *qualification=bytes?[NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL]:nil;
        result[@"fast_snapshot_codec"]=[qualification[@"fast_snapshot_codec_max"] isEqual:@3]?@3:
            [qualification[@"fast_snapshot_codec"] isEqual:@2]?@2:@1;
        result[@"fast_patch_version"]=[qualification[@"fast_snapshot_codec_max"] isEqual:@3]?@2:@1;
    }
    if (displayInfo) result[@"display_ready"] = @NO;
    if (openCheck && access == kIOHIDAccessTypeGranted && target && ![result[@"ambiguous"] boolValue]) {
        result[@"open_attempted"] = @YES;
        IOReturn opened = IOHIDDeviceOpen(target, kIOHIDOptionsTypeNone);
        result[@"open_status"] = status(opened);
        if (opened == kIOReturnSuccess) {
            NSString *serial=identity(property(target,@"SerialNumber"));
            if(serial)result[@"device_identity_sha256"]=serial;
            uint8_t flags;
            if(observePadding && display_preflight(target,&flags,result))test_reply(target,NULL,flags,result);
            if (displayInfo) result[@"display_ready"] = @(display_preflight(target, &flags, result));
            if (displayLength && !interrupted && display_preflight(target, &flags, result)) {
                displaySent = display[0] == 3 ? test_reply(target, display, flags, result) :
                    (display[0] == 4 || display[0] == 5) ? settings_request(target, display, displayLength, flags, result) :
                    send_display(target, display, displayLength, flags, result);
            }
            if (ledTest && !interrupted) {
                // Read only the existing Num Lock output element, never an input element.
                CFArrayRef elements = IOHIDDeviceCopyMatchingElements(target, (__bridge CFDictionaryRef)
                    @{@"UsagePage": @8, @"Usage": @1, @"Type": @(kIOHIDElementTypeOutput)}, 0);
                if (elements && CFArrayGetCount(elements) == 1) {
                    IOHIDElementRef element = (IOHIDElementRef)CFArrayGetValueAtIndex(elements, 0);
                    if (IOHIDElementGetType(element) != kIOHIDElementTypeOutput ||
                        IOHIDElementGetUsagePage(element) != 8 || IOHIDElementGetUsage(element) != 1) {
                        result[@"led_probe"] = @"Refused an element that is not the Num Lock output";
                        CFRelease(elements); elements = NULL;
                    }
                    if (elements) {
                    IOHIDValueRef old = NULL;
                    IOReturn read = IOHIDDeviceGetValue(target, element, &old);
                    result[@"output_value_read_status"] = status(read);
                    if (read == kIOReturnSuccess && old) {
                        CFIndex previous = IOHIDValueGetIntegerValue(old);
                        if (previous == 0 || previous == 1) {
                            CFRetain(old);
                            IOHIDValueRef next = IOHIDValueCreateWithIntegerValue(kCFAllocatorDefault, element, 0, !previous);
                            result[@"led_write_attempted"] = @YES;
                            result[@"led_write_status"] = status(IOHIDDeviceSetValue(target, element, next));
                            usleep(150000);
                            result[@"led_restore_status"] = status(IOHIDDeviceSetValue(target, element, old));
                            CFRelease(next); CFRelease(old);
                        }
                    }
                    }
                } else result[@"led_probe"] = @"Exactly one Num Lock output element is required";
                if (elements) CFRelease(elements);
            }
            result[@"close_status"] = status(IOHIDDeviceClose(target, kIOHIDOptionsTypeNone));
        }
    }
    if (devices) CFRelease(devices);
    CFRelease(manager);
    if (displayLength) result[@"display_reports_written"] = @(displaySent);
    result[@"interrupted"] = @(interrupted != 0);
    NSData *encoded = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];
    NSError *error = nil;
    if (![encoded writeToFile:receipt options:NSDataWritingAtomic error:&error]) {
        fprintf(stderr, "Cannot save probe receipt\n"); return 1;
    }
    chmod(receipt.fileSystemRepresentation, 0600);
    puts([[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding].UTF8String);
    return interrupted || (displayLength && !displaySent) ? 1 : 0;
 }
}
