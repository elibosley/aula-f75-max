#pragma once

/* Experimental wired target. Pins recovered from the preserved supplier image. */
#define DEBOUNCE 5
#define MATRIX_IO_DELAY 10
#define ENCODER_RESOLUTION 4
#define SPI_DRIVER SPID0
#define SPI_SCK_PIN D0
#define SPI_MOSI_PIN D2
#define SPI_MISO_PIN NO_PIN
#define SPI_SELECT_MODE SPI_SELECT_MODE_NONE
#define DYNAMIC_KEYMAP_LAYER_COUNT 1
#define NO_ACTION_ONESHOT
#define NO_ACTION_TAPPING


/* Wireless input must continue when USB is absent or suspended. */
#define NO_USB_STARTUP_CHECK
