"""Reglas de selección y recomendación para pasajeros."""
from dataclasses import dataclass


@dataclass
class EstadoBus:
    ocupacion: int
    capacidad_maxima: int
    llegada_min: float


# Compatibilidad con la versión anterior (antes de conectar SUMO).
DATOS_DEMO = {
    "P1": EstadoBus(12, 50, 2.0),
    "P2": EstadoBus(32, 50, 4.0),
    "P3": EstadoBus(46, 50, 7.0),
}


def recomendar(estado):
    porcentaje = estado.ocupacion / max(estado.capacidad_maxima, 1)
    if porcentaje >= .9:
        return "Bus casi lleno; considera esperar el siguiente."
    if estado.llegada_min > 10:
        return "Llegada lejana: considera otra alternativa."
    return "Puedes esperar: hay espacio disponible."


def buses_para_parada(buses, parada):
    """Filtra vehículos cuya lista de paradas pendientes incluye la elegida."""
    disponibles = [
        bus for bus in buses
        if parada in bus.get("paradas_pendientes", ())
        and bus.get("eta", {}).get(parada) is not None
    ]
    return sorted(disponibles, key=lambda bus: bus["eta"][parada])
