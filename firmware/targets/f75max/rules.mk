CUSTOM_MATRIX = lite
OPT = 2
EEPROM_DRIVER = transient
RAW_ENABLE = yes
SRC += matrix.c panel.c studio.c recovery.S rgb.c radio.c battery.c settings.c power.c
SRC += storage_probe.c
OS_DETECTION_ENABLE = yes
LDFLAGS += -Wl,--section-start=.f75_settings_reserve=0x3f000 -Wl,--undefined=f75_settings_reserve
LDFLAGS += -Wl,--section-start=.f75_custom_reserve=0x38000 -Wl,--undefined=f75_custom_reserve
SRC += f75_custom.c f75_bundle.c f75_transfer.c f75_clock.c
SRC += f75_core.c f75_lighting.c f75_navigation.c f75_display.c f75_timer.c f75_pet.c
QUANTUM_LIB_SRC += spi_master.c
# GCC 15 diagnoses fallthrough in this pinned upstream SPI driver.
OPT_DEFS += -Wno-error=implicit-fallthrough

