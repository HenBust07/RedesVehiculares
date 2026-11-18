"""Estadistica por sonda y experimento; ninguna suma de direcciones unicas."""
import csv
import json
import math
import re
import time
from pathlib import Path
from .model import MODEL_STATUS, Parameters
from .protocol import FIELDS, IntegrityError, strict_json, validate_record
from .storage import CSV_FIELDS
from .identity import assignment


class Running:
    def __init__(self):
        self.n, self.mean, self.m2, self.scale = 0, 0.0, 0.0, 0.0

    def add(self, value):
        if value is None:
            return
        # Normalize before squaring: even finite uncalibrated estimates can overflow a naive variance.
        if abs(value) > self.scale:
            ratio = self.scale / abs(value)
            self.mean *= ratio
            self.m2 *= ratio * ratio
            self.scale = abs(value)
        normalized = value / self.scale if self.scale else 0.
        self.n += 1
        delta = normalized - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (normalized - self.mean)

    def result(self):
        return {"n": self.n, "mean": self.mean*self.scale if self.n else None,
                "sample_stddev": math.sqrt(max(0, self.m2 / (self.n - 1)))*self.scale if self.n > 1 else None}


class Statistics:
    KEYS = ("probe_requests", "unique_addresses", "rssi_mean_dbm", "estimated_people", "absolute_error", "free_heap_bytes", "dropped_events")

    def __init__(self):
        self.sensors = {}

    def add(self, row):
        sensor = row["sensor_id"]
        item = self.sensors.setdefault(sensor, {"windows": 0, "zero_probe_windows": 0,
            "metrics": {k: Running() for k in self.KEYS}})
        item["windows"] += 1
        item["zero_probe_windows"] += row["probe_requests"] == 0
        for key in self.KEYS:
            item["metrics"][key].add(row.get(key))

    def result(self):
        return {sensor: {"windows": item["windows"],
            "percent_windows_without_probes": 100 * item["zero_probe_windows"] / item["windows"],
            **{key: value.result() for key, value in item["metrics"].items()},
            "model_status": MODEL_STATUS,
            "warning": "Ventanas sin probes NO prueban ausencia de personas; no hay fusion de sondas"}
            for sensor, item in self.sensors.items()}


def load_experiment(path):
    path = Path(path)
    if path.is_file():
        path = path.parent
    for attempt in range(8):
        try:
            metadata_text = (path / "metadata.json").read_text(encoding="utf-8-sig")
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(.02 * (attempt + 1))
    if len(metadata_text) > 128000:
        raise ValueError("Metadatos demasiado grandes")
    meta = strict_json(metadata_text)
    if meta.get("schema_version") != 1 or meta.get("data_source") not in ("real", "synthetic"):
        raise ValueError("Solo experimentos del laboratorio con origen declarado")
    origin = meta.get("host_origin_monotonic_ns")
    if type(origin) is not int or origin < 0:
        raise ValueError("Falta referencia temporal del computador")
    source = path / "observations.jsonl"
    if source.stat().st_size > 128_000_000:
        raise ValueError("Archivo excede el limite local de 128 MB")
    rows, warnings, previous = [], [], {}
    stats = Statistics()
    with source.open(encoding="utf-8") as stream:
        try:
            for index, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                if index > 50000 or len(line) > 8192:
                    raise IntegrityError("HISTORY_SIZE_LIMIT")
                row = strict_json(line)
                legacy_fields=set(CSV_FIELDS)-{'bus_id','probe_id'}
                if set(row) not in (set(CSV_FIELDS),legacy_fields) or row["data_source"] != meta["data_source"] or row["experiment_id"] != meta["experiment_id"]:
                    raise IntegrityError("HISTORY_SCHEMA_OR_SOURCE")
                if 'bus_id' in row and ({k:row[k] for k in ('bus_id','probe_id')} != assignment(row['sensor_id'])
                        or meta.get('probe_assignments',{}).get(row['sensor_id']) != assignment(row['sensor_id'])):
                    raise IntegrityError('HISTORY_PROBE_BUS_MAPPING')
                validate_record({k: row[k] for k in FIELDS})
                if (type(row["host_monotonic_ns"]) is not int or row["host_monotonic_ns"] < origin
                        or type(row["host_elapsed_s"]) not in (int, float)
                        or not math.isclose(row["host_elapsed_s"], (row["host_monotonic_ns"]-origin)/1e9, abs_tol=1e-6)
                        or type(row["segment_id"]) is not int or row["segment_id"] < 1
                        or row["model_status"] != MODEL_STATUS):
                    raise IntegrityError("HISTORY_CLOCK_OR_MODEL")
                port_pattern=r'COM\d+' if meta['data_source']=='real' else r'SIM_BUS_00[12]'
                if not isinstance(row['port'],str) or not re.fullmatch(port_pattern,row['port']) or row['port']!=meta['ports'].get(row['sensor_id']):
                    raise IntegrityError('HISTORY_PORT_MAPPING')
                key = row["sensor_id"], row["segment_id"]
                if key in previous and row["window_start_ms"] != previous[key] + 10000:
                    raise IntegrityError("HISTORY_WINDOW_SEQUENCE")
                if row["manual_count"] is not None and (type(row["manual_count"]) is not int or row["manual_count"] < 0):
                    raise IntegrityError("HISTORY_MANUAL_COUNT")
                if row["estimated_people"] is not None:
                    if type(row['estimated_people']) not in (int,float) or not math.isfinite(row['estimated_people']):
                        raise IntegrityError('HISTORY_ESTIMATE_TYPE')
                    expected = Parameters(row["B"], row["pd"]).estimate(row["unique_addresses"])
                    if not math.isclose(expected, row["estimated_people"], rel_tol=1e-10, abs_tol=1e-10):
                        raise IntegrityError("HISTORY_ESTIMATE")
                    error = abs(expected-row["manual_count"]) if row["manual_count"] is not None else None
                    if row["absolute_error"] != error:
                        raise IntegrityError("HISTORY_ABSOLUTE_ERROR")
                elif any(row[k] is not None for k in ("B", "pd", "absolute_error")):
                    raise IntegrityError("HISTORY_DISABLED_MODEL")
                previous[key] = row["window_start_ms"]
                rows.append(row)
                stats.add(row)
        except (ValueError, TypeError, KeyError, UnicodeError):
            warnings.append("Archivo incompleto/corrupto: se muestra solo el prefijo valido; no se rellenan datos")
    manual=[]
    try:
        with (path/'manual_counts.csv').open(encoding='utf-8-sig',newline='') as stream:
            for count in csv.DictReader(stream):
                stamp,value=int(count['host_monotonic_ns']),int(count['count'])
                if stamp<origin or value<0 or count['data_source']!=meta['data_source']:
                    raise ValueError('Invalid manual timeline')
                manual.append(((stamp-origin)/1e9,value))
        manual.sort()
    except (OSError,ValueError,KeyError):
        warnings.append('Linea temporal manual incompleta; se conserva lo valido, sin inventar observaciones')
    return {"path": str(path), "metadata": meta, "rows": rows, "manual":manual,
            "statistics": stats.result(), "warnings": warnings}


def export_csv(dataset, destination):
    with Path(destination).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, CSV_FIELDS)
        writer.writeheader()
        writer.writerows(dataset["rows"])
