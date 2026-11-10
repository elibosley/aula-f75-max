// SPDX-License-Identifier: MIT
// A permission-gated, enrolled-device-only Bluetooth output probe.
// No input callbacks, input reports, event taps, device seizure or flash writes.
#import <Foundation/Foundation.h>
#import <IOKit/hid/IOHIDManager.h>
#import <IOKit/hidsystem/IOHIDLib.h>
#import <CommonCrypto/CommonDigest.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

static volatile sig_atomic_t interrupted;
static void stop(int sig) { interrupted = sig; }
static id property(IOHIDDeviceRef device, NSString *key) {
    return CFBridgingRelease(IORegistryEntryCreateCFProperty(IOHIDDeviceGetService(device),
        (__bridge CFStringRef)key, kCFAllocatorDefault, 0));
}
static NSString *identity(NSString *serial) {
    if (![serial isKindOfClass:[NSString class]] || !serial.length) return nil;
    NSData *data = [serial dataUsingEncoding:NSUTF8StringEncoding];
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
    NSMutableString *result = [NSMutableString string];
    for (unsigned i = 0; i < sizeof(digest); ++i) [result appendFormat:@"%02x", digest[i]];
    return result;
}
static NSString *status(IOReturn result) { return [NSString stringWithFormat:@"0x%08x", result]; }

int main(int argc, const char **argv) {
 @autoreleasepool {
    BOOL request = NO, openCheck = NO, ledTest = NO;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--check")) continue;
        else if (!strcmp(argv[i], "--request-access")) request = YES;
        else if (!strcmp(argv[i], "--open-check")) openCheck = YES;
        else if (!strcmp(argv[i], "--led-test")) ledTest = openCheck = YES;
        else { fprintf(stderr, "Use --check, --request-access, --open-check, or --led-test\n"); return 2; }
    }
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
        @"permission_requested": @(prompted), @"reads_keystrokes": @NO,
        @"input_callbacks_registered": @NO, @"writes_flash": @NO,
        @"open_requested": @(openCheck), @"open_attempted": @NO, @"led_write_attempted": @NO
    } mutableCopy];
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
        unsigned owners = 0;
        for (id board in [bindings[@"boards"] allValues]) {
            if ([board isKindOfClass:[NSDictionary class]] && serial && [board[slot] isEqual:serial]) ++owners;
        }
        [matches addObject:@{@"slot": @([slot intValue]), @"enrolled_owners": @(owners)}];
        if (owners == 1) { if (target) { result[@"ambiguous"] = @YES; } else target = device; }
    }
    result[@"candidate_metadata"] = candidates;
    result[@"local_wireless_devices"] = matches;
    if (openCheck && access == kIOHIDAccessTypeGranted && target && ![result[@"ambiguous"] boolValue]) {
        result[@"open_attempted"] = @YES;
        IOReturn opened = IOHIDDeviceOpen(target, kIOHIDOptionsTypeNone);
        result[@"open_status"] = status(opened);
        if (opened == kIOReturnSuccess) {
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
    result[@"interrupted"] = @(interrupted != 0);
    NSData *encoded = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:NULL];
    NSError *error = nil;
    if (![encoded writeToFile:receipt options:NSDataWritingAtomic error:&error]) {
        fprintf(stderr, "Cannot save probe receipt\n"); return 1;
    }
    chmod(receipt.fileSystemRepresentation, 0600);
    puts([[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding].UTF8String);
    return interrupted ? 1 : 0;
 }
}
