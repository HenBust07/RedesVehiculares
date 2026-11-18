"""Emulacion en memoria, SIN radio ni puertos COM. Solo datos SINTETICOS."""
import json
import queue
import threading
import time
from .protocol import SENSORS, TEST_NAMES


def synthetic_record(sensor="BUS_001", start_ms=100, unique=3):
    processed = unique * 2
    return {"sensor_id": sensor, "window_start_ms": start_ms, "window_duration_ms": 10000,
        "channel": 6, "probe_requests": processed, "unique_addresses": unique,
        "rssi_mean_dbm": -60.0 if processed else None, "rssi_min_dbm": -70 if processed else None,
        "rssi_max_dbm": -50 if processed else None, "dropped_events": 0, "free_heap_bytes": 222000,
        "processed_events": processed, "unique_overflow_events": 0, "boundary_rejected_events": 0,
        "queue_peak": 1 if processed else 0, "rotation_gap_us": 100}


def boot_lines():
    for name in sorted(TEST_NAMES):
        yield "#TEST " + json.dumps({"name": name, "source": "synthetic_in_memory", "pass": True, "observed": 1, "expected": 1})
    yield "#SELFTEST passed=19 total=19 failed=0 radio_started=0"
    yield "#MEMORY queue_buffer_bytes=1536 unique_table_bytes=4096 worker_stack_bytes=6144"
    yield "#READY selftests=PASS radio_disabled=1 commands=START,STOP session_windows=12"


class SyntheticPort:
    def __init__(self, sensor, interval, fault=None):
        self.sensor, self.interval, self.fault = sensor, interval, fault
        self.timeout, self.port, self.is_open, self.dtr = .03, None, False, False
        self._rts = False
        self.data = queue.Queue()
        self.pending = bytearray()
        self.halt = threading.Event()
        self.lock = threading.RLock()
        self.generator = None
        self.rows, self.clock_ms = 0, 100
        self.active = False
        self.writes = []

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, value):
        old, self._rts = self._rts, value
        if old and not value and self.is_open:
            self.halt.set()
            self.active = False
            self.clock_ms = 100
            for line in boot_lines():
                self.put(line)

    def put(self, line):
        self.data.put(line if isinstance(line, bytes) else (line + "\n").encode("utf-8"))

    @property
    def in_waiting(self):
        return len(self.pending) or (1 if not self.data.empty() else 0)

    def open(self):
        self.is_open = True

    def reset_input_buffer(self):
        self.pending.clear()
        while not self.data.empty():
            self.data.get_nowait()

    def read(self, size):
        if not self.is_open:
            raise OSError("synthetic disconnection")
        if not self.pending:
            try:
                self.pending.extend(self.data.get(timeout=self.timeout))
            except queue.Empty:
                return b""
        result = bytes(self.pending[:size])
        del self.pending[:size]
        return result

    def write(self, data):
        if not self.is_open:
            raise OSError("closed synthetic port")
        self.writes.append(data)
        if data == b"START\n":
            self.halt = threading.Event()
            self.rows, self.active = 0, True
            self.put("#STATE wifi_initialized mode=NULL promiscuous=1 channel=6 passive=1")
            self.put("#STATE capture_started windows=12 window_ms=10000")
            self.generator = threading.Thread(target=self._generate, args=(self.halt,), daemon=True)
            self.generator.start()
        elif data == b"STOP\n":
            with self.lock:
                self.halt.set()
                if self.active:
                    self.active = False
                    self.put("#STATE partial_window_discarded reason=STOP")
                    self.put(f"#STATE capture_stopped windows={self.rows} elapsed_ms={self.rows*10000} wifi_stop=ESP_OK")
        return len(data)

    def _generate(self, halt):
        for index in range(12):
            if halt.wait(self.interval):
                return
            with self.lock:
                if halt.is_set() or not self.is_open:
                    return
                fault = self.fault if index == 1 else None
                if fault == "disconnect":
                    self.is_open = False
                    return
                if fault == "restart":
                    self.put("rst:0xc (SW_CPU_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)")
                    return
                if fault == "silent":
                    return
                if fault == "corrupt":
                    self.put(b'{"sensor_id":\xff}\n')
                    return
                start = self.clock_ms + (10000 if fault == "gap" else -10000 if fault == "duplicate" else 0)
                sensor = SENSORS[1] if self.fault == "identity" and self.sensor == SENSORS[0] else self.sensor
                row = synthetic_record(sensor, start, unique=(index + (self.sensor == "BUS_002")) % 5)
                if fault == 'schema':
                    row['ssid'] = 'FORBIDDEN_SYNTHETIC_FIELD'
                self.put(json.dumps(row))
                self.clock_ms += 10000
                self.rows += 1
                if index == 11:
                    self.active = False
                    self.put("#STATE capture_stopped windows=12 elapsed_ms=120000 wifi_stop=ESP_OK")

    def flush(self):
        pass

    def close(self):
        self.halt.set()
        self.is_open = False


class SyntheticPorts:
    data_source = "synthetic"

    def __init__(self, interval=1.0, faults=None):
        self.interval, self.faults, self.instances = interval, faults or {}, {}

    def ports(self):
        return [{"port": "SIM_" + sensor, "description": "SINTETICO en memoria, sin radio",
                 "vid": 0x1A86 if sensor == "BUS_001" else 0x10C4,
                 "pid": 0x7523 if sensor == "BUS_001" else 0xEA60} for sensor in SENSORS]

    def create(self, sensor, port):
        assert port == "SIM_" + sensor
        self.instances[sensor] = SyntheticPort(sensor, self.interval, self.faults.get(sensor))
        return self.instances[sensor]
