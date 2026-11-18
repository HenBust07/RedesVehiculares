"""Protocolo estricto del firmware V1 existente, sin comandos de identidad/AP."""
import json
import math
import re

SENSORS = ("BUS_001", "BUS_002")
FIELDS = frozenset(("sensor_id", "window_start_ms", "window_duration_ms", "channel",
    "probe_requests", "unique_addresses", "rssi_mean_dbm", "rssi_min_dbm", "rssi_max_dbm",
    "dropped_events", "free_heap_bytes", "processed_events", "unique_overflow_events",
    "boundary_rejected_events", "queue_peak", "rotation_gap_us"))
TEST_NAMES = frozenset(("siphash_official_length6_vector", "valid_probe_request", "reject_beacon",
    "reject_data", "reject_probe_response", "reject_all_33_truncations", "reject_ie_overrun",
    "reject_protected_frame", "reject_fragment", "three_probes_two_addresses",
    "repeated_identifier_not_double_counted", "rssi_statistics", "key_rotation_changes_token",
    "window_reset_erases_counts", "window_reset_erases_tokens", "reject_cross_window_timestamps",
    "actual_freertos_queue_saturation", "queue_conservation", "bounded_unique_table"))


class IntegrityError(ValueError):
    """El mensaje es estatico: nunca incluir la linea recibida en registros."""


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise IntegrityError("JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    def constant(_):
        raise IntegrityError("JSON_NONFINITE")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, IntegrityError):
            raise
        raise IntegrityError("INVALID_JSON") from None
    if not isinstance(value, dict):
        raise IntegrityError("JSON_NOT_OBJECT")
    return value


def validate_record(row, expected=None):
    if not isinstance(row, dict) or set(row) != FIELDS:
        raise IntegrityError("AGGREGATE_FIELDS")
    if row["sensor_id"] not in SENSORS or (expected and row["sensor_id"] != expected):
        raise IntegrityError("IDENTITY_MISMATCH")
    if row["channel"] != 6 or row["window_duration_ms"] != 10000:
        raise IntegrityError("UNSUPPORTED_CONFIGURATION")
    for key in FIELDS - {"sensor_id", "rssi_mean_dbm", "rssi_min_dbm", "rssi_max_dbm"}:
        if type(row[key]) is not int or not 0 <= row[key] < 2**63:
            raise IntegrityError("INVALID_INTEGER")
    if row["probe_requests"] != row["processed_events"] + row["dropped_events"]:
        raise IntegrityError("QUEUE_CONSERVATION")
    if not 0 <= row["unique_addresses"] <= min(row["processed_events"], 512):
        raise IntegrityError("UNIQUE_COUNT")
    if row["queue_peak"] > 64 or row["free_heap_bytes"] <= 0:
        raise IntegrityError("MEMORY_OR_QUEUE")
    rssi = [row[k] for k in ("rssi_min_dbm", "rssi_mean_dbm", "rssi_max_dbm")]
    if row["processed_events"] == 0:
        if rssi != [None, None, None]:
            raise IntegrityError("EMPTY_RSSI")
    elif (not all(type(v) in (int, float) and math.isfinite(v) and -127 <= v <= 0 for v in rssi)
          or rssi != sorted(rssi)):
        raise IntegrityError("RSSI_RANGE")
    return row


class Monitor:
    """Una maquina de estados por puerto. Identidad real solo al primer JSON."""
    def __init__(self, expected):
        if expected not in SENSORS:
            raise ValueError("Sonda desconocida")
        self.expected = expected
        self.tests = set()
        self.test_summary = False
        self.ready = False
        self.mode = "boot"
        self.identity_verified = False
        self.previous = None
        self.last_device_ms = None
        self.rows = 0
        self.wifi_verified = False

    def request_start(self):
        if not self.ready or self.mode != "ready":
            raise IntegrityError("START_BEFORE_READY")
        self.mode = "starting"
        self.previous = None
        self.rows = 0
        self.wifi_verified = False

    def request_stop(self):
        if self.mode in ("starting", "capture"):
            self.mode = "stopping"

    def consume(self, raw):
        if len(raw) > 4096:
            raise IntegrityError("OVERLONG_LINE")
        try:
            line = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            if self.mode == "boot" and not self.tests:
                return "boot_noise", {"byte_count": len(raw)}
            raise IntegrityError("CORRUPT_UTF8") from None
        if not line:
            return "ignored", {}
        if "\ufffd" in line:
            raise IntegrityError("CORRUPT_UNICODE")
        if line.startswith("{"):
            if self.mode not in ("capture", "stopping") or not self.wifi_verified:
                raise IntegrityError("AGGREGATE_OUTSIDE_CAPTURE")
            row = validate_record(strict_json(line), self.expected)
            if self.previous is not None:
                start, previous = row["window_start_ms"], self.previous["window_start_ms"]
                if start == previous:
                    raise IntegrityError("DUPLICATE_WINDOW")
                if start < previous:
                    raise IntegrityError("DEVICE_CLOCK_RESET")
                if start != previous + 10000:
                    raise IntegrityError("MISSING_WINDOW")
            elif self.last_device_ms is not None and row["window_start_ms"] <= self.last_device_ms:
                raise IntegrityError("DEVICE_CLOCK_RESET")
            self.previous = row
            self.last_device_ms = row["window_start_ms"]
            self.rows += 1
            if self.rows > 12:
                raise IntegrityError("TOO_MANY_WINDOWS")
            self.identity_verified = True
            return "record", row
        if line.startswith("#TEST "):
            if self.ready:
                raise IntegrityError("UNEXPECTED_RESTART")
            test = strict_json(line[6:])
            if (set(test) != {"name", "source", "pass", "observed", "expected"}
                    or not isinstance(test["name"], str) or test["name"] not in TEST_NAMES or test["name"] in self.tests
                    or test["source"] != "synthetic_in_memory" or test["pass"] is not True
                    or type(test["observed"]) is not int or type(test["expected"]) is not int
                    or test["observed"] != test["expected"]):
                raise IntegrityError("SELFTEST_FAILED_OR_DUPLICATE")
            self.tests.add(test["name"])
            return "selftest", {"passed": len(self.tests)}
        if line.startswith("#SELFTEST"):
            if self.ready:
                raise IntegrityError("UNEXPECTED_RESTART")
            if line != "#SELFTEST passed=19 total=19 failed=0 radio_started=0" or self.tests != TEST_NAMES:
                raise IntegrityError("SELFTEST_SUMMARY")
            self.test_summary = True
            return "selftests_ok", {"passed": 19}
        if line.startswith("#MEMORY "):
            if self.ready or not self.test_summary:
                raise IntegrityError("UNEXPECTED_MEMORY_DIAGNOSTIC")
            if line != "#MEMORY queue_buffer_bytes=1536 unique_table_bytes=4096 worker_stack_bytes=6144":
                raise IntegrityError("UNSUPPORTED_MEMORY_CONFIGURATION")
            return "configuration", {"channel_configured": 6, "window_ms": 10000, "session_windows": 12,
                                      "baud": 115200, "channel_effective": None}
        if line.startswith("#READY"):
            if self.ready:
                raise IntegrityError("UNEXPECTED_RESTART")
            if (line != "#READY selftests=PASS radio_disabled=1 commands=START,STOP session_windows=12"
                    or not self.test_summary or self.tests != TEST_NAMES):
                raise IntegrityError("READY_WITHOUT_TESTS")
            self.ready, self.mode = True, "ready"
            return "ready", {"tests_passed": 19, "radio_disabled": True, "identity_verified": False}
        if line.startswith("#STATE wifi_initialized"):
            if self.mode not in ("starting", "stopping") or line != "#STATE wifi_initialized mode=NULL promiscuous=1 channel=6 passive=1":
                raise IntegrityError("WIFI_STATE")
            self.wifi_verified = True
            return "wifi", {"channel_effective": 6, "passive": True}
        if line.startswith("#STATE capture_started"):
            if self.mode not in ("starting", "stopping") or not self.wifi_verified or line != "#STATE capture_started windows=12 window_ms=10000":
                raise IntegrityError("CAPTURE_STATE")
            if self.mode != "stopping":
                self.mode = "capture"
            return "started", {"windows": 12, "window_ms": 10000}
        if line == "#STATE partial_window_discarded reason=STOP":
            if self.mode != "stopping":
                raise IntegrityError("UNEXPECTED_PARTIAL_WINDOW")
            return "partial_discarded", {"intentional": True}
        if line.startswith("#STATE capture_stopped"):
            match = re.fullmatch(r"#STATE capture_stopped windows=(\d+) elapsed_ms=(\d+) wifi_stop=ESP_OK", line)
            if not match or self.mode not in ("capture", "stopping"):
                raise IntegrityError("STOP_NOT_CONFIRMED")
            count, elapsed = map(int, match.groups())
            intentional = self.mode == "stopping"
            if count != self.rows or (not intentional and count != 12):
                raise IntegrityError("MISSING_WINDOW_AT_STOP")
            self.mode = "ready"
            return "stopped", {"windows": count, "device_elapsed_ms": elapsed, "intentional": intentional,
                                "radio_stop_confirmed": True}
        if self.ready or line.startswith("#ERROR"):
            if "rst:" in line or line.startswith(("ets ", "ESP-ROM", "#SELFTEST", "Guru")):
                raise IntegrityError("UNEXPECTED_RESTART")
            raise IntegrityError("UNEXPECTED_SERIAL_LINE")
        # ROM/bootloader preamble is not experiment data and is never saved verbatim.
        return "boot_preamble", {}
