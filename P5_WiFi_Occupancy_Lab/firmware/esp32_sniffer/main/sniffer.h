#pragma once
#include "probe_core.h"
#include "esp_err.h"

typedef struct {
    uint32_t accepted;
    uint32_t dropped;
    uint32_t boundary_rejected;
    uint32_t queue_peak;
} p5_rx_counts_t;

bool p5_queue_init(void);
int64_t p5_window_open(const uint8_t key[16], int64_t start_us, int64_t end_us);
p5_rx_counts_t p5_window_close(void);
bool p5_receive_event(p5_event_t *event, unsigned timeout_ms);
void p5_clear_queue(void); /* Only after p5_window_close, with no consumer. */
void p5_ingest(const uint8_t *frame, size_t length, int8_t rssi, uint8_t channel,
               int64_t timestamp_us);
bool p5_selftests(void);
esp_err_t p5_wifi_start_passive(void);
esp_err_t p5_wifi_stop_passive(void);
void p5_worker(void *argument);
