#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include "sniffer.h"
#include "driver/uart.h"
#include "esp_event.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

static StaticEventGroup_t command_control;
static StaticTask_t worker_control;
static StackType_t worker_stack[CONFIG_P5_WORKER_STACK_BYTES / sizeof(StackType_t)];
_Static_assert(CONFIG_P5_WORKER_STACK_BYTES % sizeof(StackType_t) == 0, "Worker stack must be word aligned");
_Static_assert(CONFIG_P5_UART_BAUD == CONFIG_ESP_CONSOLE_UART_BAUDRATE, "UART/console baud mismatch");

void app_main(void)
{
    /* Suppress SDK informational logs that might include a hardware MAC.
     * Application diagnostics always start with #, aggregates with {. */
    esp_log_level_set("*", ESP_LOG_ERROR);
    setvbuf(stdout, NULL, _IOLBF, 0);
    /* Configure the UART before test output: changing the UART after printing
     * can discard bytes still in its TX FIFO and truncate a JSON diagnostic. */
    const uart_config_t uart = {
        .baud_rate = CONFIG_P5_UART_BAUD, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT
    };
    esp_err_t error = uart_param_config(UART_NUM_0, &uart);
    if (error == ESP_OK) { error = uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0); }
    if (error != ESP_OK) {
        printf("#ERROR uart code=%s\n", esp_err_to_name(error));
        return;
    }
    for (const char *p = CONFIG_P5_SENSOR_ID; *p; ++p) {
        if (!isalnum((unsigned char)*p) && *p != '_' && *p != '-') {
            printf("#ERROR invalid_sensor_id\n");
            return;
        }
    }
    if (!CONFIG_P5_SENSOR_ID[0] || !p5_queue_init()) {
        printf("#ERROR invalid_sensor_or_queue\n");
        return;
    }
    if (!p5_selftests()) {
        printf("#ERROR selftest_failed radio_disabled=1\n");
        return;
    }
    error = esp_event_loop_create_default();
    if (error != ESP_OK) {
        printf("#ERROR event_loop code=%s\n", esp_err_to_name(error));
        return;
    }
    EventGroupHandle_t commands = xEventGroupCreateStatic(&command_control);
    if (!commands || !xTaskCreateStaticPinnedToCore(p5_worker, "p5_process",
        sizeof(worker_stack), commands, 5, worker_stack, &worker_control, 1)) {
        printf("#ERROR worker_allocation\n");
        return;
    }
    printf("#MEMORY queue_buffer_bytes=%u unique_table_bytes=%u worker_stack_bytes=%u\n",
           (unsigned)(CONFIG_P5_QUEUE_CAPACITY * sizeof(p5_event_t)),
           (unsigned)(CONFIG_P5_UNIQUE_CAPACITY * sizeof(uint64_t)), (unsigned)sizeof(worker_stack));
    printf("#READY selftests=PASS radio_disabled=1 commands=START,STOP session_windows=%d\n", CONFIG_P5_SESSION_WINDOWS);
    char command[16] = {0};
    size_t used = 0;
    for (;;) {
        uint8_t byte;
        if (uart_read_bytes(UART_NUM_0, &byte, 1, pdMS_TO_TICKS(100)) != 1) { continue; }
        if (byte == '\n' || byte == '\r') {
            command[used] = 0;
            if (strcmp(command, "START") == 0) {
                xEventGroupSetBits(commands, BIT0);
            } else if (strcmp(command, "STOP") == 0) {
                xEventGroupSetBits(commands, BIT1);
            } else if (used) { printf("#ERROR unknown_command\n"); }
            used = 0;
        } else if (used + 1 < sizeof(command)) {
            command[used++] = byte;
        } else {
            used = 0;
            printf("#ERROR command_too_long\n");
        }
    }
}
