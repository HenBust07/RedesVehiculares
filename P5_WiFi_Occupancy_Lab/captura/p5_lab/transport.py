"""Un lector y una cola de comandos por sonda; nunca llama a Tkinter."""
import queue
import re
import threading
import time

from .protocol import IntegrityError, Monitor


class RealPorts:
    data_source = "real"

    def ports(self):
        from serial.tools import list_ports
        return [{"port": p.device, "description": p.description, "vid": p.vid, "pid": p.pid}
                for p in list_ports.comports() if re.fullmatch(r"COM\d+", p.device, re.I)]

    def create(self, sensor, port):
        import serial
        return serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=0.7,
                             rtscts=False, dsrdtr=False)


class SerialWorker(threading.Thread):
    def __init__(self, sensor, port, provider, emit, *, window_timeout=15.0, boot_timeout=15.0):
        super().__init__(name=f"P5-{sensor}", daemon=True)
        self.sensor, self.port, self.provider, self.emit = sensor, port, provider, emit
        self.commands = queue.Queue(maxsize=16)
        self.monitor = Monitor(sensor)
        self.window_timeout, self.boot_timeout = window_timeout, boot_timeout
        self.segment = 0

    def command(self, command, segment=0):
        try:
            self.commands.put_nowait((command, segment))
        except queue.Full:
            self.emit(self.sensor, "fault", {"code": "COMMAND_QUEUE_FULL"})

    def run(self):
        connection = None
        pending = bytearray()
        deadline = time.monotonic() + self.boot_timeout
        closing = False
        radio_stopped = False
        reset_requested = False

        def send(command):
            data = (command + "\n").encode("ascii")
            if connection.write(data) != len(data):
                raise IntegrityError("SHORT_SERIAL_WRITE")
            connection.flush()

        try:
            connection = self.provider.create(self.sensor, self.port)
            connection.dtr, connection.rts = False, True
            connection.port = self.port
            connection.open()
            connection.reset_input_buffer()
            time.sleep(0.15)
            connection.rts = False
            self.emit(self.sensor, "opened", {"port": self.port, "reset_requested": True})
            while True:
                try:
                    command, segment = self.commands.get_nowait()
                except queue.Empty:
                    command = None
                if command == "START":
                    self.monitor.request_start()
                    self.segment, radio_stopped = segment, False
                    send("START")
                    deadline = time.monotonic() + self.window_timeout
                elif command in ("STOP", "CLOSE"):
                    closing = closing or command == "CLOSE"
                    if self.monitor.mode in ("starting", "capture"):
                        self.monitor.request_stop()
                        send("STOP")
                        deadline = time.monotonic() + 4
                    elif closing and self.monitor.mode in ("ready", "boot"):
                        break
                chunk = connection.read(max(1, min(connection.in_waiting, 1024)))
                pending.extend(chunk)
                while b"\n" in pending:
                    raw, _, pending = pending.partition(b"\n")
                    kind, payload = self.monitor.consume(bytes(raw))
                    if kind == "record":
                        payload = {"record": payload, "segment_id": self.segment}
                        if self.monitor.mode != "stopping":
                            deadline = time.monotonic() + self.window_timeout
                    elif kind == "started":
                        # Firmware clears STOP at START: repeat STOP after startup if requested meanwhile.
                        if self.monitor.mode == "stopping":
                            send("STOP")
                            deadline = time.monotonic() + 4
                        else:
                            deadline = time.monotonic() + self.window_timeout
                    elif kind == "stopped":
                        radio_stopped = True
                        payload["segment_id"] = self.segment
                    if kind not in ("ignored", "boot_preamble"):
                        self.emit(self.sensor, kind, payload)
                if len(pending) > 4096:
                    raise IntegrityError("OVERLONG_LINE")
                if closing and self.monitor.mode == "ready":
                    break
                if self.monitor.mode != "ready" and time.monotonic() > deadline:
                    if self.monitor.mode == "boot":
                        raise IntegrityError("BOOT_READY_TIMEOUT")
                    if self.monitor.mode == "stopping":
                        raise IntegrityError("STOP_ACK_TIMEOUT")
                    raise IntegrityError("MISSING_WINDOW_TIMEOUT")
        except IntegrityError as exc:
            self.emit(self.sensor, "fault", {"code": str(exc)})
        except Exception:
            # Do not persist exception strings, which may contain USB identifiers or received bytes.
            self.emit(self.sensor, "fault", {"code": "SERIAL_IO_OR_DISCONNECTION"})
        finally:
            if connection is not None:
                try:
                    if connection.is_open and self.monitor.mode in ("starting", "capture", "stopping"):
                        try:
                            send("STOP")
                        finally:
                            # If transport is damaged, request a reset to the known radio-off boot.
                            # This is a request, not proof of an electrically effective reset.
                            connection.rts = True
                            time.sleep(0.15)
                            connection.rts = False
                            reset_requested = True
                except Exception:
                    pass
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass
            self.emit(self.sensor, "closed", {"port_closed": connection is None or not connection.is_open,
                "radio_stop_confirmed": radio_stopped or self.monitor.mode == "ready",
                "reset_requested_after_unconfirmed_stop": reset_requested})
