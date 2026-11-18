#include "probe_core.h"
#include <limits.h>
#include <string.h>

void p5_secure_zero(void *memory, size_t length)
{
    volatile uint8_t *p = memory;
    while (length--) { *p++ = 0; }
}

bool p5_probe_valid(const uint8_t *frame, size_t length_with_fcs)
{
    /* Driver sig_len includes four FCS bytes (ESP-IDF ESP32 native RX ABI).
     * Never cast a potentially unaligned frame to an IEEE 802.11 struct. */
    if (!frame || length_with_fcs < 33 || length_with_fcs > CONFIG_P5_MAX_FRAME_BYTES) {
        return false;
    }
    const uint16_t fc = (uint16_t)frame[0] | ((uint16_t)frame[1] << 8);
    /* Version 0, management, subtype 4. Reject DS/protected/order/more-fragment
     * variants unsupported by this deliberately narrow parser. Retry is allowed. */
    if ((fc & 0x00ff) != 0x0040 || (fc & 0xc700) != 0 ||
        (frame[22] & 0x0f) != 0 || (frame[10] & 1) != 0) {
        return false;
    }
    uint8_t source_or = 0;
    for (size_t i = 10; i < 16; ++i) { source_or |= frame[i]; }
    if (!source_or) { return false; }
    const size_t end = length_with_fcs - 4;
    bool ssid_seen = false;
    bool rates_seen = false;
    for (size_t offset = 24; offset < end;) {
        if (end - offset < 2) { return false; }
        const uint8_t id = frame[offset];
        const size_t size = frame[offset + 1];
        offset += 2;
        if (size > end - offset) { return false; }
        if (id == 0) {
            if (ssid_seen || size > 32) { return false; }
            ssid_seen = true;
        }
        if (id == 1) {
            if (rates_seen || size < 1 || size > 8) { return false; }
            rates_seen = true;
        }
        /* Only inspect IE boundaries; never copy/log SSID or any IE content. */
        offset += size;
    }
    return ssid_seen && rates_seen;
}

static uint64_t read_le64(const uint8_t *p)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < 8; ++i) { value |= (uint64_t)p[i] << (8 * i); }
    return value;
}

static uint64_t rotl(uint64_t x, unsigned b) { return (x << b) | (x >> (64 - b)); }
#define SIPROUND() do { \
    v0 += v1; v1 = rotl(v1, 13); v1 ^= v0; v0 = rotl(v0, 32); \
    v2 += v3; v3 = rotl(v3, 16); v3 ^= v2; \
    v0 += v3; v3 = rotl(v3, 21); v3 ^= v0; \
    v2 += v1; v1 = rotl(v1, 17); v1 ^= v2; v2 = rotl(v2, 32); \
} while (0)

uint64_t p5_siphash6(const uint8_t source[6], const uint8_t key[16])
{
    /* Fixed six-byte SipHash-2-4, 128-bit key / 64-bit result. Algorithm from
     * Aumasson/Bernstein CC0 reference: github.com/veorq/SipHash.
     * Bounded short-message PRF, no malloc and no heavyweight crypto context.
     * Official length-6 known-answer vector is checked on every boot. */
    const uint64_t k0 = read_le64(key), k1 = read_le64(key + 8);
    uint64_t v0 = UINT64_C(0x736f6d6570736575) ^ k0;
    uint64_t v1 = UINT64_C(0x646f72616e646f6d) ^ k1;
    uint64_t v2 = UINT64_C(0x6c7967656e657261) ^ k0;
    uint64_t v3 = UINT64_C(0x7465646279746573) ^ k1;
    uint64_t block = UINT64_C(6) << 56;
    for (unsigned i = 0; i < 6; ++i) { block |= (uint64_t)source[i] << (8 * i); }
    v3 ^= block;
    SIPROUND(); SIPROUND();
    v0 ^= block;
    v2 ^= 0xff;
    SIPROUND(); SIPROUND(); SIPROUND(); SIPROUND();
    const uint64_t result = v0 ^ v1 ^ v2 ^ v3;
    /* No input address or key is copied to heap/queue. Compiler register
     * spills are ephemeral; the application retains only the keyed token. */
    return result;
}

void p5_stats_reset(p5_stats_t *stats)
{
    p5_secure_zero(stats, sizeof(*stats));
    stats->rssi_min = INT8_MAX;
    stats->rssi_max = INT8_MIN;
}

void p5_stats_add(p5_stats_t *stats, const p5_event_t *event)
{
    ++stats->processed;
    stats->rssi_sum += event->rssi;
    if (event->rssi < stats->rssi_min) { stats->rssi_min = event->rssi; }
    if (event->rssi > stats->rssi_max) { stats->rssi_max = event->rssi; }
    /* Zero is the vacant sentinel; remapping one PRF output adds negligible
     * collision probability. Results are an approximate address count. */
    const uint64_t token = event->token ? event->token : 1;
    size_t index = (size_t)(token % CONFIG_P5_UNIQUE_CAPACITY);
    for (size_t i = 0; i < CONFIG_P5_UNIQUE_CAPACITY; ++i) {
        if (stats->tokens[index] == token) { return; }
        if (!stats->tokens[index]) {
            stats->tokens[index] = token;
            ++stats->unique;
            return;
        }
        index = (index + 1) % CONFIG_P5_UNIQUE_CAPACITY;
    }
    ++stats->unique_overflow_events;
}
