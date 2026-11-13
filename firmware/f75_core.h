/* Portable interface core. Hardware adapters are deliberately separate. */
#ifndef F75_CORE_H
#define F75_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum { F75_HOSTS = 5, F75_RECORD_BYTES = 160, F75_TILE_ROWS = 8 };
typedef enum { F75_MAC, F75_WINDOWS, F75_ANDROID } f75_os;
typedef enum { F75_BALANCED, F75_ENDURANCE, F75_DESK } f75_power;
typedef enum { F75_ACTIVE, F75_DIM, F75_OFF, F75_SLEEP } f75_stage;
typedef enum { F75_PAIR_IDLE, F75_PAIR_CONFIRM, F75_PAIR_WAIT, F75_PAIR_TIMEOUT } f75_pair_phase;
typedef struct {
    uint8_t os[F75_HOSTS];
    char names[F75_HOSTS][19];
    uint8_t active_host, bonded_mask, caps_swap, power, brightness, speed;
    uint8_t effect, wheel, face, reduced_motion;
    uint8_t color[3];
    uint8_t light_mode;
    uint8_t os_auto_mask;
    uint8_t companion;
} f75_config;
typedef struct {
    f75_config config;
    uint32_t last_activity, pair_started, transaction, release_epoch;
    uint8_t pair_slot, connected_slot;
    f75_pair_phase pairing;
    bool control_layer;
} f75_state;
typedef struct { f75_stage stage; uint8_t rgb, screen, animation_fps; } f75_budget;

void f75_defaults(f75_config *config);
bool f75_config_valid(const f75_config *config);
const char *f75_color_name(const f75_config *config);
void f75_cycle_color(f75_config *config);
void f75_init(f75_state *state, const f75_config *config, uint32_t now);
uint16_t f75_map_usage(const f75_state *state, uint16_t physical_usage);
/* Default Fn+Caps toggles Caps Lock on Mac; explicit custom bindings win. */
uint16_t f75_map_layer_usage(const f75_state *state, uint16_t physical_usage, bool fn);
bool f75_set_os(f75_state *state, f75_os os);
bool f75_detect_os(f75_state *state,uint8_t slot,f75_os os);
bool f75_host_os_hint(f75_state *state,uint8_t slot,f75_os os,uint32_t transaction,bool connected);
void f75_set_caps_swap(f75_state *state, bool enabled);
void f75_set_control_layer(f75_state *state, bool enabled);
void f75_activity(f75_state *state, uint32_t now);
uint32_t f75_switch_host(f75_state *state, uint8_t slot, uint32_t now);
bool f75_pair_request(f75_state *state, uint8_t slot, uint32_t now);
uint32_t f75_pair_confirm(f75_state *state, uint32_t held_ms, uint32_t now);
bool f75_host_ack(f75_state *state, uint8_t slot, uint32_t transaction);
void f75_pair_cancel(f75_state *state);
void f75_tick(f75_state *state, uint32_t now);
f75_budget f75_power_budget(const f75_state *state, uint32_t now, uint8_t battery, bool usb_power);
void f75_record_encode(const f75_config *config, uint32_t generation, uint8_t record[F75_RECORD_BYTES]);
bool f75_record_decode(const uint8_t record[F75_RECORD_BYTES], f75_config *config, uint32_t *generation);
/* The flash adapter writes the inactive record first, verifies it, then retains both records.
   Returning a record here does not itself implement flash writes or atomicity. */
bool f75_record_select(const uint8_t a[F75_RECORD_BYTES], const uint8_t b[F75_RECORD_BYTES], f75_config *config, uint32_t *generation);
uint32_t f75_crc32(const uint8_t *data,size_t length);
#endif
