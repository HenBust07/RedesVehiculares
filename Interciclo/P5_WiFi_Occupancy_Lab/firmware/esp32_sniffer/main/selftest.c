#include "sniffer.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

static p5_stats_t test_stats;
static unsigned failures, test_count;

static void check(const char *name, bool pass, uint32_t observed, uint32_t expected)
{
    ++test_count;
    if (!pass) { ++failures; }
    printf("#TEST {\"name\":\"%s\",\"source\":\"synthetic_in_memory\","
           "\"pass\":%s,\"observed\":%" PRIu32 ",\"expected\":%" PRIu32 "}\n",
           name, pass ? "true" : "false", observed, expected);
}

static void consume(void)
{
    p5_event_t event;
    while (p5_receive_event(&event, 0)) { p5_stats_add(&test_stats, &event); }
    p5_secure_zero(&event, sizeof(event));
}

bool p5_selftests(void)
{
    /* These bytes represent artificial frames, never sent to the radio. */
    uint8_t probe[33] = {0};
    probe[0] = 0x40;
    memset(probe + 4, 0xff, 6);
    probe[10] = 0x02;
    probe[15] = 0x01;
    memset(probe + 16, 0xff, 6);
    probe[24] = 0; probe[25] = 0; /* Wildcard SSID IE, not a real SSID. */
    probe[26] = 1; probe[27] = 1; probe[28] = 0x82;
    uint8_t key_a[16], key_b[16];
    for (unsigned i = 0; i < 16; ++i) { key_a[i] = i; key_b[i] = i + 32; }
    const uint8_t message[6] = {0, 1, 2, 3, 4, 5};
    const bool crypto_ok = p5_siphash6(message, key_a) == UINT64_C(0xcbc9466e58fee3ce);
    check("siphash_official_length6_vector", crypto_ok, crypto_ok, 1);
    check("valid_probe_request", p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 1);
    probe[0] = 0x80;
    check("reject_beacon", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[0] = 0x08;
    check("reject_data", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[0] = 0x50;
    check("reject_probe_response", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[0] = 0x40;
    unsigned rejected = 0;
    for (size_t length = 0; length < sizeof(probe); ++length) {
        rejected += !p5_probe_valid(probe, length);
    }
    check("reject_all_33_truncations", rejected == sizeof(probe), rejected, sizeof(probe));
    probe[27] = 8;
    check("reject_ie_overrun", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[27] = 1;
    probe[1] = 0x40;
    check("reject_protected_frame", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[1] = 0;
    probe[22] = 1;
    check("reject_fragment", !p5_probe_valid(probe, sizeof(probe)), p5_probe_valid(probe, sizeof(probe)), 0);
    probe[22] = 0;

    p5_stats_reset(&test_stats);
    p5_window_open(key_a, 0, 1000);
    p5_ingest(probe, sizeof(probe), -40, CONFIG_P5_CHANNEL, 100);
    p5_ingest(probe, sizeof(probe), -50, CONFIG_P5_CHANNEL, 200);
    probe[15] = 2;
    p5_ingest(probe, sizeof(probe), -60, CONFIG_P5_CHANNEL, 300);
    p5_rx_counts_t counts = p5_window_close();
    consume();
    check("three_probes_two_addresses", counts.accepted == 3 && test_stats.unique == 2,
          test_stats.unique, 2);
    check("repeated_identifier_not_double_counted", test_stats.processed == 3 && test_stats.unique == 2,
          test_stats.processed, 3);
    check("rssi_statistics", test_stats.rssi_min == -60 && test_stats.rssi_max == -40 &&
          test_stats.rssi_sum == -150, (uint32_t)(-test_stats.rssi_sum), 150);
    const uint64_t token_a = p5_siphash6(probe + 10, key_a);
    const uint64_t token_b = p5_siphash6(probe + 10, key_b);
    check("key_rotation_changes_token", token_a != token_b, token_a != token_b, 1);
    p5_stats_reset(&test_stats);
    check("window_reset_erases_counts", test_stats.unique == 0 && test_stats.processed == 0,
          test_stats.processed, 0);
    bool erased = true;
    for (size_t i = 0; i < CONFIG_P5_UNIQUE_CAPACITY; ++i) { erased &= test_stats.tokens[i] == 0; }
    check("window_reset_erases_tokens", erased, erased, 1);
    p5_clear_queue();

    p5_window_open(key_b, 100, 200);
    p5_ingest(probe, sizeof(probe), -50, CONFIG_P5_CHANNEL, 99);
    p5_ingest(probe, sizeof(probe), -50, CONFIG_P5_CHANNEL, 200);
    counts = p5_window_close();
    check("reject_cross_window_timestamps", counts.boundary_rejected == 2 && counts.accepted == 0,
          counts.boundary_rejected, 2);
    p5_clear_queue();

    p5_window_open(key_b, 0, 1000);
    for (unsigned i = 0; i < CONFIG_P5_QUEUE_CAPACITY + 7; ++i) {
        p5_ingest(probe, sizeof(probe), -50, CONFIG_P5_CHANNEL, 500);
    }
    counts = p5_window_close();
    consume();
    check("actual_freertos_queue_saturation", counts.dropped == 7 && counts.queue_peak == CONFIG_P5_QUEUE_CAPACITY,
          counts.dropped, 7);
    check("queue_conservation", test_stats.processed + counts.dropped == counts.accepted,
          test_stats.processed + counts.dropped, counts.accepted);
    p5_clear_queue();

    p5_stats_reset(&test_stats);
    for (uint64_t i = 1; i <= CONFIG_P5_UNIQUE_CAPACITY + 3; ++i) {
        const p5_event_t event = {.token = i, .rssi = -50};
        p5_stats_add(&test_stats, &event);
    }
    check("bounded_unique_table", test_stats.unique == CONFIG_P5_UNIQUE_CAPACITY && test_stats.unique_overflow_events == 3,
          test_stats.unique_overflow_events, 3);
    p5_stats_reset(&test_stats);
    p5_secure_zero(key_a, sizeof(key_a));
    p5_secure_zero(key_b, sizeof(key_b));
    p5_secure_zero(probe, sizeof(probe));
    printf("#SELFTEST passed=%u total=%u failed=%u radio_started=0\n", test_count - failures, test_count, failures);
    return failures == 0;
}
