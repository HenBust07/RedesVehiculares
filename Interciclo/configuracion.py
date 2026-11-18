"""Parámetros de la interfaz y del servidor SUMO en Docker."""
HOST = "127.0.0.1"
PUERTO = 3400
PASO_SUMO_S = 1.0
INTERVALO_PANTALLA_MS = 150  # ~6.7 segundos SUMO por segundo real
CAPACIDAD_BUS = 50
VELOCIDAD_ETA_M_S = 8.0  # estimación provisional, no predicción de tráfico

PARADAS = {
    "P1": {"nombre": "Av. Ordóñez Lasso, 552", "x": 7734.10, "y": 9076.45,
           "edge": "480936970#1", "pos": 137.03},
    "P2": {"nombre": "Ciudad de Cuenca", "x": 7957.27, "y": 9005.72,
           "edge": "480936970#3", "pos": 52.75},
    "P3": {"nombre": "Hotel Oro Verde", "x": 8212.14, "y": 8938.92,
           "edge": "480936970#4", "pos": 224.09},
}

# Ocupación ilustrativa; se reemplazará por abordajes y descensos reales.
OCUPACION_DEMO = {"bus_001": 12, "bus_002": 32, "bus_003": 46,
                  "bus_004": 28, "bus_005": 36}

# Archivo opcional exportado desde SUMO para dibujar calles reales.
ARCHIVO_MAPA = "mapa_linea3.json"
