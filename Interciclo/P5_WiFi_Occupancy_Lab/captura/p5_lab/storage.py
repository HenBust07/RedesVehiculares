"""Persistencia local incremental. JSONL es la fuente autoritativa de ventanas."""
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from .model import MODEL_STATUS
from .identity import BUS_ID, assignment

CSV_FIELDS = ["data_source", "experiment_id", "sensor_id", "bus_id", "probe_id", "port", "segment_id", "host_received_utc",
    "host_monotonic_ns", "host_elapsed_s", "window_start_ms", "window_duration_ms", "channel",
    "probe_requests", "unique_addresses", "rssi_mean_dbm", "rssi_min_dbm", "rssi_max_dbm",
    "dropped_events", "processed_events", "unique_overflow_events", "boundary_rejected_events", "queue_peak",
    "rotation_gap_us", "free_heap_bytes", "B", "pd", "estimated_people", "manual_count",
    "absolute_error", "model_status", "manual_reference"]


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def private_text(text):
    text = re.sub(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", "[identificador omitido]", str(text))
    return "".join(c for c in text[:2000] if c in "\n\t" or ord(c) >= 32)


def check_space(path, minimum=1_500_000_000):
    paths = [Path(path)]
    if os.name == "nt":
        paths += [Path("C:/"), Path("D:/")]
    if any(shutil.disk_usage(p).free < minimum for p in paths if p.exists()):
        raise OSError("STORAGE_MARGIN_BELOW_1_5_GB")


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(8):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            # Windows may briefly deny replacement while history opens metadata for reading.
            if attempt == 7:
                raise
            time.sleep(.02 * (attempt + 1))


class ExperimentStore:
    def __init__(self, root, plan, source, origin_ns, ports):
        if source not in ("real", "synthetic"):
            raise ValueError("Origen obligatorio")
        check_space(root)
        self.closed = False
        self.id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10]
        branch = "synthetic" if source == "synthetic" else "raw"
        self.path = Path(root) / "data" / branch / "p5_lab" / self.id
        self.path.mkdir(parents=True, exist_ok=False)
        self.source = source
        self.metadata = {"schema_version": 1, "application": "P5 WiFi Occupancy Lab V1", "experiment_id": self.id,
            "data_source": source, "created_utc": utc_now(), "host_origin_monotonic_ns": origin_ns,
            "clock_reference": "PC monotonic_ns; receipt time, NOT synchronized device window boundaries",
            "model_status": MODEL_STATUS, "formula": "max(0, (D-B)/pd)", "status": "in_progress",
            "plan": asdict(plan), "ports": ports, "channel": 6, "baud": 115200,
            "bus_id": BUS_ID, "probe_assignments": {key: assignment(key) for key in ports},
            "identity_fields": "sensor_id = ID serial heredado, no bus; probe_id = sonda; bus_id = bus compartido",
            "preset_definition": "Plantillas propuestas V1, no protocolo de rubrica",
            "manual_reference": "Ultimo aforo observado al recibir en PC, sin sincronizacion exacta con la ventana"}
        for key, val in self.metadata["plan"].items():
            if isinstance(val, str):
                self.metadata["plan"][key] = private_text(val)
        write_json(self.path / "metadata.json", self.metadata)
        self.jsonl = (self.path / "observations.jsonl").open("x", encoding="utf-8")
        self.csv_stream = (self.path / "observations.csv").open("x", encoding="utf-8-sig", newline="")
        self.csv = csv.DictWriter(self.csv_stream, CSV_FIELDS)
        self.csv.writeheader()
        self.events = (self.path / "events.jsonl").open("x", encoding="utf-8")
        self.manual_stream = (self.path / "manual_counts.csv").open("x", encoding="utf-8-sig", newline="")
        self.manual_csv = csv.DictWriter(self.manual_stream, ["host_monotonic_ns", "host_utc", "count", "data_source"])
        self.manual_csv.writeheader()

    def _flush(self, stream):
        stream.flush()
        os.fsync(stream.fileno())

    def observation(self, row):
        check_space(self.path)
        self.jsonl.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        self._flush(self.jsonl)
        self.csv.writerow(row)
        self._flush(self.csv_stream)

    def event(self, code, stamp, detail=None):
        # detail is structured application information, never a raw serial line.
        self.events.write(json.dumps({"code": code, "host_monotonic_ns": stamp, "host_utc": utc_now(),
            "data_source": self.source, "detail": detail or {}}, ensure_ascii=False, allow_nan=False) + "\n")
        self._flush(self.events)

    def manual(self, stamp, count):
        self.manual_csv.writerow({"host_monotonic_ns": stamp, "host_utc": utc_now(), "count": count, "data_source": self.source})
        self._flush(self.manual_stream)
        self.event("MANUAL_COUNT", stamp, {"count": count})

    def finish(self, status, reason, elapsed, summary):
        if self.closed:
            return
        try:
            self.metadata.update(status=status, reason=reason, finished_utc=utc_now(), active_elapsed_s=elapsed)
            write_json(self.path / "metadata.json", self.metadata)
            write_json(self.path / "summary.json", summary)
        finally:
            self.closed = True
            for stream in (self.jsonl, self.csv_stream, self.events, self.manual_stream):
                stream.close()

    def record_closure(self, sensor, stamp, detail):
        """Confirmation can arrive after the experiment files were finalized."""
        self.metadata.setdefault("port_closure", {})[sensor] = detail
        write_json(self.path / "metadata.json", self.metadata)
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"code": "PORT_CLOSED", "host_monotonic_ns": stamp,
                "host_utc": utc_now(), "data_source": self.source,
                "detail": {"sensor": sensor, **detail}}, allow_nan=False) + "\n")
            self._flush(stream)
