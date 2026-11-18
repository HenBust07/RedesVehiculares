#include "sniffer.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "esp_event.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/task.h"

static StaticQueue_t queue_control;
static uint8_t queue_memory[CONFIG_P5_QUEUE_CAPACITY * sizeof(p5_event_t)] __attribute__((aligned(4)));
static QueueHandle_t queue;
static portMUX_TYPE rx_lock = portMUX_INITIALIZER_UNLOCKED;
static uint8_t ephemeral_key[16];
static int64_t window_start, window_end;
static bool accepting;
static p5_rx_counts_t rx_counts;
static p5_stats_t stats;
static bool wifi_initialized, wifi_started;

bool p5_queue_init(void)
{
    queue = xQueueCreateStatic(CONFIG_P5_QUEUE_CAPACITY, sizeof(p5_event_t), queue_memory, &queue_control);
    return queue != NULL;
}

int64_t p5_window_open(const uint8_t key[16], int64_t start_us, int64_t end_us)
{
    portENTER_CRITICAL(&rx_lock);
    memcpy(ephemeral_key, key, sizeof(ephemeral_key));
    window_start = start_us;
    window_end = end_us;
    memset(&rx_counts, 0, sizeof(rx_counts));
    accepting = true;
    const int64_t gap = esp_timer_get_time() - start_us;
    portEXIT_CRITICAL(&rx_lock);
    return gap > 0 ? gap : 0;
}

p5_rx_counts_t p5_window_close(void)
{
    portENTER_CRITICAL(&rx_lock);
    accepting = false;
    p5_secure_zero(ephemeral_key, sizeof(ephemeral_key));
    const p5_rx_counts_t snapshot = rx_counts;
    portEXIT_CRITICAL(&rx_lock);
    return snapshot;
}

bool p5_receive_event(p5_event_t *event, unsigned timeout_ms)
{
    return xQueueReceive(queue, event, pdMS_TO_TICKS(timeout_ms)) == pdTRUE;
}

void p5_clear_queue(void)
{
    p5_event_t event;
    while (p5_receive_event(&event, 0)) { }
    p5_secure_zero(&event, sizeof(event));
    p5_secure_zero(queue_memory, sizeof(queue_memory));
}

void p5_ingest(const uint8_t *frame, size_t length, int8_t rssi, uint8_t channel,
               int64_t timestamp_us)
{
    if (channel != CONFIG_P5_CHANNEL || rssi > 0 || rssi < -127 ||
        !p5_probe_valid(frame, length)) { return; }
#if CONFIG_P5_RSSI_FILTER
    if (rssi < CONFIG_P5_RSSI_MIN_DBM) { return; }
#endif
    /* WiFi callback is a task, NOT an ISR. All enqueue calls have zero wait.
     * Serialize one bounded six-byte PRF + enqueue with key rotation. The
     * consumer never holds the queue lock while acquiring rx_lock. No frame,
     * MAC or IE copy enters the queue; no logging/malloc/float occurs here. */
    portENTER_CRITICAL(&rx_lock);
    if (!accepting) { portEXIT_CRITICAL(&rx_lock); return; }
    if (timestamp_us < window_start || timestamp_us >= window_end) {
        ++rx_counts.boundary_rejected;
        portEXIT_CRITICAL(&rx_lock);
        return;
    }
    p5_event_t event = {
        .token = p5_siphash6(frame + 10, ephemeral_key),
        .timestamp_us = timestamp_us, .rssi = rssi, .channel = channel
    };
    ++rx_counts.accepted;
    if (xQueueSend(queue, &event, 0) != pdTRUE) {
        ++rx_counts.dropped;
    } else {
        const uint32_t depth = uxQueueMessagesWaiting(queue);
        if (depth > rx_counts.queue_peak) { rx_counts.queue_peak = depth; }
    }
    portEXIT_CRITICAL(&rx_lock);
    p5_secure_zero(&event, sizeof(event));
}

static void rx_callback(void *buffer, wifi_promiscuous_pkt_type_t type)
{
    if (!buffer || type != WIFI_PKT_MGMT) { return; }
    const wifi_promiscuous_pkt_t *packet = buffer;
    if (packet->rx_ctrl.rx_state != 0) { return; }
    p5_ingest(packet->payload, packet->rx_ctrl.sig_len, packet->rx_ctrl.rssi,
              packet->rx_ctrl.channel, esp_timer_get_time());
}

esp_err_t p5_wifi_start_passive(void)
{
    wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
    config.nvs_enable = 0; /* Do not erase or use the pre-existing NVS. */
    esp_err_t error = esp_wifi_init(&config);
    if (error != ESP_OK) { return error; }
    wifi_initialized = true;
#define WIFI_CHECK(call) do { error = (call); if (error != ESP_OK) { return error; } } while (0)
    WIFI_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    WIFI_CHECK(esp_wifi_set_mode(WIFI_MODE_NULL));
    WIFI_CHECK(esp_wifi_start());
    wifi_started = true;
    WIFI_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    WIFI_CHECK(esp_wifi_set_channel(CONFIG_P5_CHANNEL, WIFI_SECOND_CHAN_NONE));
    const wifi_promiscuous_filter_t filter = {.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT};
    WIFI_CHECK(esp_wifi_set_promiscuous_filter(&filter));
    WIFI_CHECK(esp_wifi_set_promiscuous_rx_cb(rx_callback));
    WIFI_CHECK(esp_wifi_set_promiscuous(true));
    wifi_mode_t mode;
    uint8_t primary;
    wifi_second_chan_t secondary;
    bool promiscuous;
    WIFI_CHECK(esp_wifi_get_mode(&mode));
    WIFI_CHECK(esp_wifi_get_channel(&primary, &secondary));
    WIFI_CHECK(esp_wifi_get_promiscuous(&promiscuous));
    if (mode != WIFI_MODE_NULL || primary != CONFIG_P5_CHANNEL || !promiscuous) {
        return ESP_ERR_INVALID_STATE;
    }
    printf("#STATE wifi_initialized mode=NULL promiscuous=1 channel=%u passive=1\n", primary);
    return ESP_OK;
#undef WIFI_CHECK
}

esp_err_t p5_wifi_stop_passive(void)
{
    (void)p5_window_close();
    esp_err_t result = ESP_OK;
    if (wifi_started) {
        result = esp_wifi_set_promiscuous(false);
        const esp_err_t stop_error = esp_wifi_stop();
        if (result == ESP_OK) { result = stop_error; }
        wifi_started = false;
    }
    if (wifi_initialized) {
        const esp_err_t deinit_error = esp_wifi_deinit();
        if (result == ESP_OK) { result = deinit_error; }
        wifi_initialized = false;
    }
    return result;
}

static void drain_queue(void)
{
    p5_event_t event;
    while (p5_receive_event(&event, 0)) { p5_stats_add(&stats, &event); }
    p5_secure_zero(&event, sizeof(event));
    /* Queue backing storage otherwise retains copies of popped tokens. */
    p5_secure_zero(queue_memory, sizeof(queue_memory));
}

typedef struct {
    int64_t start_us;
    int64_t rotation_gap_us;
    p5_rx_counts_t rx;
    uint32_t unique, unique_overflow, processed;
    int64_t rssi_sum;
    int rssi_min, rssi_max;
} summary_t;

static void emit_summary(const summary_t *summary)
{
    char mean[32], minimum[16], maximum[16];
    if (summary->processed) {
        snprintf(mean, sizeof(mean), "%.2f", (double)summary->rssi_sum / summary->processed);
        snprintf(minimum, sizeof(minimum), "%d", summary->rssi_min);
        snprintf(maximum, sizeof(maximum), "%d", summary->rssi_max);
    } else {
        strcpy(mean, "null"); strcpy(minimum, "null"); strcpy(maximum, "null");
    }
    printf("{\"sensor_id\":\"%s\",\"window_start_ms\":%" PRId64
           ",\"window_duration_ms\":%d,\"channel\":%d,\"probe_requests\":%" PRIu32
           ",\"unique_addresses\":%" PRIu32 ",\"rssi_mean_dbm\":%s,\"rssi_min_dbm\":%s"
           ",\"rssi_max_dbm\":%s,\"dropped_events\":%" PRIu32 ",\"free_heap_bytes\":%" PRIu32
           ",\"processed_events\":%" PRIu32 ",\"unique_overflow_events\":%" PRIu32
           ",\"boundary_rejected_events\":%" PRIu32 ",\"queue_peak\":%" PRIu32
           ",\"rotation_gap_us\":%" PRId64 "}\n",
           CONFIG_P5_SENSOR_ID, summary->start_us / 1000, CONFIG_P5_WINDOW_MS, CONFIG_P5_CHANNEL,
           summary->rx.accepted, summary->unique, mean, minimum, maximum, summary->rx.dropped,
           esp_get_free_heap_size(), summary->processed, summary->unique_overflow,
           summary->rx.boundary_rejected, summary->rx.queue_peak, summary->rotation_gap_us);
    fflush(stdout);
}

void p5_worker(void *argument)
{
    EventGroupHandle_t commands = argument;
    for (;;) {
        (void)xEventGroupWaitBits(commands, BIT0, pdTRUE, pdFALSE, portMAX_DELAY);
        xEventGroupClearBits(commands, BIT1);
        esp_err_t error = p5_wifi_start_passive();
        if (error != ESP_OK) {
            printf("#ERROR wifi_start code=%s\n", esp_err_to_name(error));
            (void)p5_wifi_stop_passive();
            continue;
        }
        /* RF enabled and power-save disabled: esp_fill_random has an active
         * hardware entropy source per ESP-IDF RNG documentation. */
        uint8_t key[16];
        esp_fill_random(key, sizeof(key));
        const int64_t origin = esp_timer_get_time();
        int64_t start = origin;
        const int64_t duration = (int64_t)CONFIG_P5_WINDOW_MS * 1000;
        p5_stats_reset(&stats);
        int64_t rotation_gap = p5_window_open(key, start, start + duration);
        p5_secure_zero(key, sizeof(key));
        printf("#STATE capture_started windows=%d window_ms=%d\n", CONFIG_P5_SESSION_WINDOWS, CONFIG_P5_WINDOW_MS);
        bool stopped = false;
        unsigned completed = 0;
        for (unsigned index = 0; index < CONFIG_P5_SESSION_WINDOWS; ++index) {
            const int64_t end = start + duration;
            while (esp_timer_get_time() < end) {
                if (xEventGroupGetBits(commands) & BIT1) { stopped = true; break; }
                p5_event_t event;
                if (p5_receive_event(&event, 10)) { p5_stats_add(&stats, &event); }
                p5_secure_zero(&event, sizeof(event));
            }
            const p5_rx_counts_t counts = p5_window_close();
            drain_queue();
            if (stopped) {
                p5_stats_reset(&stats);
                printf("#STATE partial_window_discarded reason=STOP\n");
                break;
            }
            const summary_t summary = {
                .start_us = start, .rotation_gap_us = rotation_gap, .rx = counts,
                .unique = stats.unique, .unique_overflow = stats.unique_overflow_events,
                .processed = stats.processed, .rssi_sum = stats.rssi_sum,
                .rssi_min = stats.rssi_min, .rssi_max = stats.rssi_max
            };
            p5_stats_reset(&stats); /* Tokens erased before opening the next window. */
            start = end;
            if (index + 1 < CONFIG_P5_SESSION_WINDOWS) {
                esp_fill_random(key, sizeof(key));
                rotation_gap = p5_window_open(key, start, start + duration);
                p5_secure_zero(key, sizeof(key));
            }
            emit_summary(&summary);
            ++completed;
        }
        p5_secure_zero(key, sizeof(key));
        p5_stats_reset(&stats);
        error = p5_wifi_stop_passive();
        printf("#STATE capture_stopped windows=%u elapsed_ms=%" PRId64 " wifi_stop=%s\n",
               completed, (esp_timer_get_time() - origin) / 1000, esp_err_to_name(error));
        xEventGroupClearBits(commands, BIT0 | BIT1);
    }
}
