#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integra la ubicación de hospitales, la flota inicial aleatoria y una
ambulancia de prueba VCM -> IESS_JCA despachada en t=120 s.
"""

# ============================================================================
# PARTE 0 — IMPORTACIONES Y CONFIGURACIÓN GENERAL
# ============================================================================
import argparse
import csv
import os
import random
import sys
from collections import deque
from pathlib import Path

SUMO_HOME = os.environ.get("SUMO_HOME", "/usr/share/sumo")
SUMO_TOOLS = os.path.join(SUMO_HOME, "tools")
if SUMO_TOOLS not in sys.path:
    sys.path.insert(0, SUMO_TOOLS)

try:
    import sumolib
    import traci
except ImportError as exc:
    raise SystemExit(
        f"Falta una dependencia de SUMO: {exc}. "
        "Comprueba SUMO_HOME y PYTHONPATH."
    )

BASE = Path(__file__).resolve().parent
NET_FILE = BASE / "cuenca_ciudad.net.xml"
SUMOCFG = BASE / "cuenca_reto.sumocfg"
CSV_FILE = BASE / "tabla_hospitales.csv"
SEMILLA = 42
P_RECHAZO = 0.25  # Probabilidad reservada para la futura lógica de despacho.
TIEMPO_DESPACHO = 120
ORIGEN = "VCM"
DESTINO = "IESS_JCA"

# ============================================================================
# PARTE 2.1 — UBICACIÓN DE HOSPITALES EN LA RED DE CUENCA
# ============================================================================
# Los IDs de arista son los identificados y verificados en la red del proyecto.
HOSPITALES = {
    "VCM": {"lon": -78.992923, "lat": -2.911098, "edge": "208782596#1"},
    "IESS_JCA": {"lon": -78.970118, "lat": -2.898698, "edge": "357285817#5"},
    "MILITAR": {"lon": -79.003968, "lat": -2.903146, "edge": "334948974#1"},
    "MUNI_PAT": {"lon": -78.982263, "lat": -2.866103, "edge": "378364650#0"},
    "MUNI_VALLE": {"lon": -78.961959, "lat": -2.919522, "edge": "-171302162#23"},
    "MONTE_SINAI": {"lon": -79.007373, "lat": -2.908606, "edge": "269103111#3"},
    "DEL_RIO": {"lon": -78.960796, "lat": -2.892939, "edge": "29223060#1"},
}


def posicion_sobre_arista(edge, x, y):
    """Proyección sobre la geometría de la arista; devuelve (posición, distancia)."""
    shape = edge.getShape()
    offset, distancia = sumolib.geomhelper.polygonOffsetAndDistanceToPoint(
        (x, y), shape
    )
    # Evitar posiciones fuera del intervalo válido de la arista.
    return max(0.0, min(float(offset), edge.getLength())), float(distancia)


def generar_tabla_hospitales():
    print("\n[2.1] Cargando red y ubicando hospitales...")
    red = sumolib.net.readNet(str(NET_FILE))
    filas = []
    for nombre, info in HOSPITALES.items():
        edge = red.getEdge(info["edge"])
        x, y = red.convertLonLat2XY(info["lon"], info["lat"])
        pos, dist = posicion_sobre_arista(edge, x, y)
        calle = edge.getName() or "Sin nombre OSM"
        filas.append((nombre, info["edge"], pos, calle, dist))
        print(f"  {nombre:12} | {info['edge']:17} | "
              f"{pos:8.2f} m | {calle:30} | {dist:8.2f} m")

    with CSV_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["hospital", "arista", "posicion_m", "calle", "distancia_m"])
        for nombre, edge, pos, calle, dist in filas:
            writer.writerow([nombre, edge, f"{pos:.2f}", calle, f"{dist:.2f}"])
    print(f"  CSV generado: {CSV_FILE.name}")
    print("  Los POI visuales están definidos en hospitales.add.xml.")
    return filas


# ============================================================================
# PARTE 2.2 — FLOTA Y COLAS DE DISPONIBILIDAD (collections.deque)
# ============================================================================
# Semilla fija para repetir exactamente el reparto aleatorio.
# P_RECHAZO se declara, pero el rechazo de hospitales se implementará en la
# fase de despacho automático (fase 4); no se simula aquí.

def crear_flota():
    rng = random.Random(SEMILLA)
    flota = {}
    numero = 1
    for hospital in HOSPITALES:
        es_publico = hospital not in ("MONTE_SINAI", "DEL_RIO")
        cantidad = rng.randint(1, 3) if es_publico else rng.randint(0, 1)
        flota[hospital] = deque()
        for _ in range(cantidad):
            flota[hospital].append(f"U{numero:02d}")
            numero += 1
    print(f"\n[2.2] Flota inicial (semilla={SEMILLA}, p_rechazo={P_RECHAZO:.0%}):")
    for hospital, unidades in flota.items():
        print(f"  {hospital:12}: {len(unidades)} unidad(es) — "
              f"{', '.join(unidades) if unidades else 'ninguna'}")
    print(f"  TOTAL: {numero - 1} ambulancias")
    print("  Nota: el rechazo del 25 % todavía NO se ejecuta en esta prueba.")
    return flota


# ============================================================================
# PARTE 2.3 — AMBULANCIA DE PRUEBA: VCM -> IESS_JCA EN t = 120 s
# ============================================================================

def probar_ambulancia(gui=False):
    ejecutable = "sumo-gui" if gui else "sumo"
    # El sumocfg original contiene <remote-port value="42333"/>.
    # TraCI necesita controlar el puerto; lo anulamos con --remote-port 0.
    # Sobrescribimos salidas para no borrar estadísticas de la fase 1.
    argumentos = [
        ejecutable, "-c", str(SUMOCFG),
        "--no-step-log", "true",
        "--summary-output", str(BASE / "summary_prueba_fase2.xml"),
        "--tripinfo-output", str(BASE / "tripinfo_prueba_fase2.xml"),
        "--statistic-output", str(BASE / "stats_prueba_fase2.xml"),
        "--collision-output", str(BASE / "collisions_prueba_fase2.xml"),
    ]
    print(f"\n[2.3] Iniciando {ejecutable}; despacho en t={TIEMPO_DESPACHO} s...")
    traci.start(argumentos)
    try:
        while traci.simulation.getTime() < TIEMPO_DESPACHO:
            traci.simulationStep()

        origen_edge = HOSPITALES[ORIGEN]["edge"]
        destino_edge = HOSPITALES[DESTINO]["edge"]
        ruta = traci.simulation.findRoute(origen_edge, destino_edge, vType="ambulance")
        if not ruta.edges:
            raise RuntimeError(f"No existe ruta {ORIGEN} -> {DESTINO}")

        ruta_id = "ruta_ambulancia_fase2"
        unidad_id = "ambulancia_prueba_U01"
        traci.route.add(ruta_id, list(ruta.edges))
        traci.vehicle.add(
            vehID=unidad_id,
            routeID=ruta_id,
            typeID="ambulance",  # Definido en vtypes.add.xml
            depart="now",
            departPos="0",
        )
        traci.vehicle.setColor(unidad_id, (255, 0, 0, 255))
        t_salida = traci.simulation.getTime()
        print(f"  Ruta: {len(ruta.edges)} aristas")
        print(f"  Distancia estimada: {ruta.length:.2f} m")
        print(f"  Tiempo estimado (findRoute): {ruta.travelTime:.2f} s")

        llegada = None
        while traci.simulation.getTime() < 12600:
            traci.simulationStep()
            if unidad_id in traci.simulation.getArrivedIDList():
                llegada = traci.simulation.getTime()
                break

        if llegada is None:
            print("  La ambulancia no llegó antes del fin de la simulación.")
        else:
            real = llegada - t_salida
            diferencia = (real / ruta.travelTime - 1) * 100 if ruta.travelTime else 0
            print(f"  Llegada: t={llegada:.0f} s")
            print(f"  Tiempo real: {real:.2f} s")
            print(f"  Diferencia frente al estimado: {diferencia:+.1f} %")
        if gui:
            input("\nPresiona ENTER para cerrar SUMO-GUI...")
    finally:
        traci.close()


# ============================================================================
# PROGRAMA PRINCIPAL — EJECUCIÓN ORDENADA DE LAS TAREAS 2.1, 2.2 Y 2.3
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Práctica 4 — Fase 2 integrada")
    parser.add_argument("--gui", action="store_true", help="Visualizar prueba en SUMO-GUI")
    parser.add_argument("--solo-datos", action="store_true",
                        help="Ejecutar solo tareas 2.1 y 2.2, sin iniciar SUMO")
    args = parser.parse_args()

    for archivo in (NET_FILE, SUMOCFG):
        if not archivo.is_file():
            raise SystemExit(f"Archivo no encontrado: {archivo}")
    generar_tabla_hospitales()
    crear_flota()
    if not args.solo_datos:
        probar_ambulancia(gui=args.gui)
    print("\nFase 2: ejecución finalizada.")


if __name__ == "__main__":
    main()
