#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "sdkconfig.h"

typedef struct {
    uint64_t token;
    int64_t timestamp_us;
    int8_t rssi;
    uint8_t channel;
} p5_event_t;

typedef struct {
    uint64_t tokens[CONFIG_P5_UNIQUE_CAPACITY];
    uint32_t unique;
    uint32_t unique_overflow_events;
    uint32_t processed;
    int64_t rssi_sum;
    int8_t rssi_min;
    int8_t rssi_max;
} p5_stats_t;

bool p5_probe_valid(const uint8_t *frame, size_t length_with_fcs);
uint64_t p5_siphash6(const uint8_t source[6], const uint8_t key[16]);
void p5_secure_zero(void *memory, size_t length);
void p5_stats_reset(p5_stats_t *stats);
void p5_stats_add(p5_stats_t *stats, const p5_event_t *event);
