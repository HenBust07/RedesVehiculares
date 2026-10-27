import csv
import sumolib

from hospitales import HOSPITALES

RED = "cuenca_ciudad.net.xml"
SALIDA = "tabla_hospitales.csv"

print("Cargando red de Cuenca...")

net = sumolib.net.readNet(RED)


def calcular_posicion(punto, geometria):
    """
    Proyecta un punto sobre la geometría de una arista.
    Devuelve la posición longitudinal y la distancia
    perpendicular al punto más cercano.
    """
    import math

    mejor_distancia = float("inf")
    mejor_posicion = 0.0
    acumulado = 0.0

    for a, b in zip(geometria[:-1], geometria[1:]):

        ax, ay = a[:2]
        bx, by = b[:2]
        px, py = punto

        dx = bx - ax
        dy = by - ay

        longitud2 = dx * dx + dy * dy

        if longitud2 == 0:
            continue

        t = ((px - ax) * dx + (py - ay) * dy) / longitud2
        t = max(0.0, min(1.0, t))

        x_proy = ax + t * dx
        y_proy = ay + t * dy

        distancia = math.hypot(px - x_proy, py - y_proy)
        longitud = math.sqrt(longitud2)

        if distancia < mejor_distancia:
            mejor_distancia = distancia
            mejor_posicion = acumulado + t * longitud

        acumulado += longitud

    return mejor_posicion, mejor_distancia, acumulado


filas = []

for nombre, datos in HOSPITALES.items():

    edge_id = datos["edge"]

    edge = net.getEdge(edge_id)

    # Coordenadas geográficas del hospital
    x, y = net.convertLonLat2XY(
        datos["lon"],
        datos["lat"]
    )

    # Geometría de la arista
    geometria = edge.getShape()

    posicion_geom, distancia, longitud_geom = calcular_posicion(
        (x, y),
        geometria
    )

    # Ajustar la posición a la longitud SUMO de la arista
    longitud_sumo = edge.getLength()

    posicion = (
        posicion_geom * longitud_sumo / longitud_geom
        if longitud_geom > 0 else 0.0
    )

    calle = edge.getName()

    if not calle:
        calle = "Sin nombre OSM"

    filas.append([
        nombre,
        edge_id,
        round(posicion, 2),
        calle,
        round(distancia, 2)
    ])


# Mostrar tabla
print("\n=== TABLA A3: UBICACIÓN DE HOSPITALES ===\n")

for fila in filas:

    print(
        f"{fila[0]:15} | "
        f"{fila[1]:20} | "
        f"{fila[2]:8.2f} m | "
        f"{fila[3]:30} | "
        f"{fila[4]:8.2f} m"
    )


# Exportar CSV
with open(SALIDA, "w", newline="", encoding="utf-8-sig") as archivo:

    escritor = csv.writer(archivo)

    escritor.writerow([
        "Hospital",
        "Arista SUMO",
        "Posicion (m)",
        "Calle",
        "Distancia al hospital (m)"
    ])

    escritor.writerows(filas)


print(f"\nArchivo generado: {SALIDA}")
print(f"Hospitales registrados: {len(filas)}")
