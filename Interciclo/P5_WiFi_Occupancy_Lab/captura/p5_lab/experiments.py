"""Plantillas propuestas para V1; no son protocolos impuestos por la rubrica."""
from dataclasses import dataclass, field
from .model import Parameters

PRESETS = {
    "P0": ("Fondo", "Sin telefonos de prueba; medir el fondo sin asumir que es cero."),
    "P1": ("Reposo / pantalla activa", "Telefonos autorizados, WiFi encendido, pantalla activa, sin trafico impuesto."),
    "P2": ("Reposo / pantalla apagada", "Comparar con P1 manteniendo geometria y cantidad documentadas."),
    "P3": ("Actividad", "Actividad WiFi autorizada definida por el operador; no garantizar Probe Requests."),
    "P4": ("Distancia", "Variar distancia en experimentos separados con la misma cantidad de telefonos."),
    "P5": ("Cantidad", "Variar cantidad de telefonos sin limitarla a dos, con referencia manual."),
    "P6": ("WiFi apagado", "Control negativo de los telefonos de prueba; puede haber equipos externos."),
    "P7": ("Entradas / salidas", "Actualizar aforo manual e instantes durante la medicion."),
    "P8": ("Ubicacion", "Comparar ubicaciones documentadas sin fusionar conteos de sondas."),
    "P9": ("Escenario real autorizado", "Observacion autorizada con aforo manual; no equivale a calibracion validada."),
}


@dataclass(frozen=True)
class Plan:
    preset: str
    mode: str
    duration_s: float
    phones: int | None
    location: str
    distance: str
    wifi_state: str
    screen: str
    activity: str
    notes: str = ""
    manual_count: int | None = None
    parameters: dict[str, Parameters | None] = field(default_factory=dict)
    continue_batches: bool = False

    def validate(self):
        import math
        if self.preset not in PRESETS or self.mode not in ("Controlada", "Escenario real"):
            raise ValueError("Seleccione modalidad y plantilla P0-P9")
        if not isinstance(self.duration_s, (int, float)) or isinstance(self.duration_s, bool) or not math.isfinite(self.duration_s) or not 1 <= self.duration_s <= 86400:
            raise ValueError("Duracion entre 1 y 86400 segundos activos")
        for value in (self.phones, self.manual_count):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("Telefonos y aforo: enteros >= 0 o desconocido")
        if not self.location.strip() or not self.distance.strip() or not self.activity.strip():
            raise ValueError("Documente ubicacion, distancia y actividad")
        if self.duration_s > 120 and not self.continue_batches:
            raise ValueError("Duraciones >120 s requieren autorizar bloques sucesivos en este experimento")
        if any(key not in ("BUS_001", "BUS_002") or (value is not None and not isinstance(value, Parameters)) for key, value in self.parameters.items()):
            raise ValueError("Parametros de sonda invalidos")
        return self
