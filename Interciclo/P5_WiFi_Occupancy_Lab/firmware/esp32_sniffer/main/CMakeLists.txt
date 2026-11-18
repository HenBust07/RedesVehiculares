idf_component_register(SRCS "main.c" "probe_core.c" "sniffer.c" "selftest.c"
    INCLUDE_DIRS "." REQUIRES esp_wifi esp_event esp_timer esp_driver_uart esp_hw_support)
