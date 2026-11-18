"""Coordinador de adquisicion. Persistencia y control fuera del hilo de Tk."""
from bisect import bisect_right
from collections import deque
import copy
from dataclasses import replace
import queue
import threading
import time

from .history import Statistics
from .identity import assignment
from .model import MODEL_STATUS
from .protocol import SENSORS
from .storage import ExperimentStore, private_text, utc_now
from .transport import RealPorts, SerialWorker

ACTIVE = ("RECORDING", "PAUSING", "PAUSED", "STOPPING")


class Controller:
    def __init__(self, root, provider=None, *, worker_options=None):
        self.root, self.provider = root, provider or RealPorts()
        self.worker_options = worker_options or {}
        self.queue = queue.Queue(maxsize=2048)
        self.overflow = threading.Event()
        self.lock = threading.RLock()
        self.workers, self.selected, self.segments, self.stopped = {}, set(), {}, set()
        self.store, self.plan, self.origin, self.stats = None, None, 0, Statistics()
        self.manual, self.elapsed_before, self.active_start = [], 0.0, None
        self.shutdown_requested = False
        self.stop_target, self.stop_deadline = None, None
        self.view = {"state": "IDLE", "source": self.provider.data_source, "elapsed": 0., "duration": 120.,
            "path": None, "reason": "", "manual": [], "events": [], "summary": {},
            "samples": {s: deque(maxlen=720) for s in SENSORS},
            "devices": {s: {"status": "Desconectada", "port": None, "ready": False,
                "identity_verified": False, "channel_effective": None, "latest": None} for s in SENSORS}}
        self.thread = threading.Thread(target=self._loop, daemon=True, name="P5-coordinator")
        self.thread.start()

    def post(self, action, **data):
        self._put("command", action, data)

    def _put(self, sensor, kind, payload):
        try:
            self.queue.put_nowait((time.monotonic_ns(), sensor, kind, payload, utc_now()))
        except queue.Full:
            self.overflow.set()

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.view)

    def _device(self, sensor, **changes):
        with self.lock:
            self.view["devices"][sensor].update(changes)

    def _state(self, state, reason=""):
        with self.lock:
            self.view.update(state=state, reason=reason)

    def _event(self, event_code, stamp=None, **detail):
        stamp = stamp or time.monotonic_ns()
        with self.lock:
            self.view["events"].append({"time": utc_now(), "code": event_code, "detail": detail})
            self.view["events"] = self.view["events"][-150:]
        if self.store is not None and not self.store.closed:
            self.store.event(event_code, stamp, detail)
        elif self.store is not None and event_code == "PORT_CLOSED":
            detail = dict(detail)
            sensor = detail.pop("sensor")
            self.store.record_closure(sensor, stamp, detail)

    def _elapsed(self):
        return self.elapsed_before + ((time.monotonic_ns() - self.active_start)/1e9 if self.active_start else 0)

    def _start_segment(self, sensor, reason):
        self.segments[sensor] = self.segments.get(sensor, 0) + 1
        self.stopped.discard(sensor)
        self._event("SEGMENT_START_REQUEST", sensor=sensor, segment_id=self.segments[sensor], reason=reason)
        self.workers[sensor].command("START", self.segments[sensor])
        self._device(sensor, status="Iniciando (ID pendiente hasta JSON)" if not self.view["devices"][sensor]["identity_verified"] else "Iniciando", ready=False)

    def _request_stop(self, target, reason):
        if self.view["state"] not in ACTIVE:
            return
        if self.active_start:
            self.elapsed_before = self._elapsed()
            self.active_start = None
        self.stop_target, self.stop_deadline = target, time.monotonic() + 6
        with self.lock:
            self.view['elapsed'] = self.elapsed_before
        self._state("PAUSING" if target == "PAUSED" else "STOPPING", reason)
        # Queue STOP on ALL selected workers before any potentially failing disk write.
        for sensor in self.selected - self.stopped:
            if sensor in self.workers:
                self.workers[sensor].command("STOP")
        self._event("PAUSE_REQUEST" if target == "PAUSED" else "STOP_REQUEST", reason=reason)
        self._complete_stop_if_ready()

    def _complete_stop_if_ready(self):
        if self.stop_target and self.selected <= self.stopped:
            target, self.stop_target = self.stop_target, None
            if target == "PAUSED":
                self._state("PAUSED", "Pausa intencional: radio detenida; no hay ventanas durante la pausa")
                self._event("PAUSE_CONFIRMED")
            else:
                self._finish("COMPLETE", self.view["reason"] or "Finalizado por operador")

    def _finish(self, state, reason):
        self.active_start = None
        if self.store is not None and not self.store.closed:
            self.store.finish(state.lower(), reason, self.elapsed_before, self.stats.result())
        self._state(state, reason)
        with self.lock:
            self.view.update(elapsed=self.elapsed_before, summary=self.stats.result())
        self.stop_target = None
        for sensor, worker in list(self.workers.items()):
            self._device(sensor, ready=False, status="Cerrando puerto")
            worker.command("CLOSE")

    def _abort(self, code):
        if self.active_start:
            self.elapsed_before = self._elapsed()
            self.active_start = None
        # Close every participant. Worker waits for STOP or requests reset if no confirmation.
        for sensor in list(self.workers):
            if sensor in self.workers:
                self.workers[sensor].command("CLOSE")
        try:
            self._event("ABORT", reason=code)
            self._finish("ABORTED", code)
        except Exception:
            self._state("ABORTED", code + "; fallo de almacenamiento, conservar JSONL valido previo")
        self.stop_target = None

    def _command(self, action, data, stamp):
        state = self.view["state"]
        if action == "connect":
            sensor, port = data["sensor"], data["port"]
            if state in ACTIVE or sensor not in SENSORS or sensor in self.workers:
                raise ValueError("No conectar durante un experimento o sobre una conexion existente")
            if any(self.view["devices"][s]["port"] == port for s in self.workers):
                raise ValueError("Un puerto no puede asignarse a ambas sondas")
            ports = [p for p in self.provider.ports() if p["port"] == port]
            expected = (0x1A86, 0x7523) if sensor == "BUS_001" else (0x10C4, 0xEA60)
            if len(ports) != 1 or (ports[0]["vid"], ports[0]["pid"]) != expected:
                raise ValueError("El puente USB no corresponde a la sonda esperada; revisar placa y COM")
            worker = SerialWorker(sensor, port, self.provider, self._put, **self.worker_options)
            self.workers[sensor] = worker
            self._device(sensor, status="Conectando / autopruebas con radio apagada", port=port,
                         identity_verified=False, ready=False, port_closed=False, channel_effective=None, latest=None)
            worker.start()
        elif action == "disconnect":
            sensor = data["sensor"]
            if state in ACTIVE and sensor in self.selected:
                self._abort("OPERATOR_DISCONNECTION")
            elif sensor in self.workers:
                self.workers[sensor].command("CLOSE")
        elif action == "start":
            if state in ACTIVE:
                raise ValueError("Ya hay un experimento activo")
            plan = data["plan"].validate()
            selected = set(data["sensors"])
            if not selected or not selected <= set(self.workers) or any(not self.view["devices"][s]["ready"] for s in selected):
                raise ValueError("Seleccione sondas conectadas y con 19 autopruebas aprobadas")
            if self.provider.data_source == "real" and not data.get("authorized", False):
                raise ValueError("Confirme un entorno autorizado antes de START")
            self.plan = replace(plan, parameters=dict(plan.parameters))
            self.selected, self.segments, self.stopped = selected, {}, set()
            self.origin = stamp
            self.store = ExperimentStore(self.root, self.plan, self.provider.data_source, stamp,
                                        {s: self.view["devices"][s]["port"] for s in selected})
            self.stats, self.manual = Statistics(), []
            self.elapsed_before, self.active_start = 0.0, time.monotonic_ns()
            with self.lock:
                self.view.update(path=str(self.store.path), duration=plan.duration_s, elapsed=0., manual=[], summary={},
                                 samples={s: deque(maxlen=720) for s in SENSORS})
            self._state("RECORDING")
            for sensor in selected:
                self._device(sensor, latest=None, channel_effective=None)
            self._event("EXPERIMENT_MANUALLY_STARTED", stamp, sensors=sorted(selected), authorized_environment=True,
                        identity_limit="ID real se verifica al primer JSON; correspondencia fisica confirmada por operador")
            if plan.manual_count is not None:
                self._manual(stamp, plan.manual_count)
            for sensor in sorted(selected):
                self._start_segment(sensor, "manual_start")
        elif action == "pause":
            if state == "RECORDING":
                self._request_stop("PAUSED", "Pausa intencional del operador")
        elif action == "resume":
            if state != "PAUSED":
                raise ValueError("Solo se reanuda una pausa confirmada")
            self.active_start = stamp
            self._state("RECORDING")
            self._event("MANUAL_RESUME", stamp)
            for sensor in sorted(self.selected):
                self._start_segment(sensor, "intentional_resume")
        elif action == "stop":
            self._request_stop("COMPLETE", "Detenido por operador")
        elif action == "manual":
            if state not in ACTIVE:
                raise ValueError("El aforo se registra dentro de un experimento")
            count = data["count"]
            if type(count) is not int or count < 0:
                raise ValueError("Aforo manual: entero >= 0")
            self._manual(stamp, count)
        elif action == "note":
            if state not in ACTIVE:
                raise ValueError("Observaciones solo dentro de un experimento")
            self._event("OPERATOR_NOTE", stamp, text=private_text(data["text"]))
        elif action == "shutdown":
            self.shutdown_requested = True
            if state in ACTIVE:
                self._abort("APPLICATION_CLOSED")
            for worker in list(self.workers.values()):
                worker.command("CLOSE")

    def _manual(self, stamp, count):
        self.manual.append((stamp, count))
        self.manual.sort()
        self.store.manual(stamp, count)
        with self.lock:
            self.view["manual"] = list(self.manual)

    def _worker(self, sensor, kind, payload, stamp, received_utc):
        if kind == "ready":
            self._device(sensor, status="Lista, radio OFF; ID esperado, aun no verificado", ready=True, tests_passed=19)
        elif kind == "wifi":
            self._device(sensor, channel_effective=6, status="WiFi NULL pasivo, esperando ventana")
        elif kind == "selftest":
            self._device(sensor, status=f"Autopruebas: {payload['passed']}/19, radio OFF")
        elif kind == "record":
            if sensor not in self.selected or self.view["state"] not in ACTIVE or self.store.closed:
                self._abort("DATA_OUTSIDE_EXPERIMENT")
                return
            row = payload["record"]
            index = bisect_right(self.manual, (stamp, float("inf"))) - 1
            manual = self.manual[index][1] if index >= 0 else None
            params = self.plan.parameters.get(sensor)
            estimate = params.estimate(row["unique_addresses"]) if params else None
            saved = {**row, **assignment(sensor), "data_source": self.provider.data_source, "experiment_id": self.store.id,
                "port": self.view["devices"][sensor]["port"], "segment_id": payload["segment_id"],
                "host_received_utc": received_utc, "host_monotonic_ns": stamp, "host_elapsed_s": (stamp-self.origin)/1e9,
                "B": params.background if params else None, "pd": params.detection_probability if params else None,
                "estimated_people": estimate, "manual_count": manual,
                "absolute_error": abs(estimate-manual) if estimate is not None and manual is not None else None,
                "model_status": MODEL_STATUS, "manual_reference": "last_observation_at_host_receipt_not_synchronized"}
            if not self.view['devices'][sensor]['identity_verified']:
                self._event('IDENTITY_CONFIRMED_BY_AGGREGATE', stamp, sensor=sensor,
                            port=self.view['devices'][sensor]['port'])
            self.store.observation(saved)
            self.stats.add(saved)
            self._device(sensor, status="Identidad verificada / adquiriendo", identity_verified=True, latest=saved)
            with self.lock:
                self.view["samples"][sensor].append(saved)
                self.view["summary"] = self.stats.result()
        elif kind == "stopped":
            self.stopped.add(sensor)
            self._device(sensor, status="Radio detenida; lista", ready=True)
            self._event("RADIO_STOP_CONFIRMED", stamp, sensor=sensor, **payload)
            if self.view["state"] == "RECORDING":
                if self._elapsed() >= self.plan.duration_s:
                    self._request_stop("COMPLETE", "Duracion activa alcanzada")
                elif self.plan.continue_batches:
                    self._start_segment(sensor, "authorized_firmware_batch_boundary")
                else:
                    self._request_stop("COMPLETE", "Bloque de firmware terminado; sin renovacion automatica")
            self._complete_stop_if_ready()
        elif kind == "fault":
            self._device(sensor, status="ERROR: " + payload["code"], ready=False)
            self._event("DEVICE_FAULT", stamp, sensor=sensor, **payload)
            if self.view["state"] in ACTIVE:
                self._abort(sensor + ": " + payload["code"])
        elif kind == "closed":
            # Remove dead worker BEFORE any disk operation can fail; shutdown must never wait on it.
            self.workers.pop(sensor, None)
            self._device(sensor, status="Puerto cerrado" + ("; parada radio no confirmada" if not payload["radio_stop_confirmed"] else ""),
                         ready=False, port_closed=payload["port_closed"])
            self._event("PORT_CLOSED", stamp, sensor=sensor, **payload)
            if self.view["state"] in ACTIVE and sensor in self.selected:
                self._abort(sensor + ": DISCONNECTION")
        elif kind in ("partial_discarded", "boot_noise", "selftests_ok", "configuration", "started"):
            self._event(kind.upper(), stamp, sensor=sensor, **payload)

    def _loop(self):
        while True:
            if self.overflow.is_set():
                self.overflow.clear()
                self._abort("HOST_EVENT_QUEUE_OVERFLOW")
            try:
                stamp, source, kind, payload, received_utc = self.queue.get(timeout=0.05)
                if source == "command":
                    try:
                        self._command(kind, payload, stamp)
                    except ValueError as exc:
                        self._event("OPERATOR_VALIDATION", stamp, message=private_text(exc))
                else:
                    self._worker(source, kind, payload, stamp, received_utc)
            except queue.Empty:
                pass
            except Exception:
                self._abort("HOST_STORAGE_OR_PROCESSING_FAILURE")
            if self.view["state"] == "RECORDING":
                elapsed = self._elapsed()
                with self.lock:
                    self.view["elapsed"] = elapsed
                if elapsed >= self.plan.duration_s:
                    self._request_stop("COMPLETE", "Duracion activa alcanzada")
            if self.stop_target and time.monotonic() > self.stop_deadline:
                self._abort("STOP_CONFIRMATION_TIMEOUT")
            if self.shutdown_requested and not self.workers:
                break
