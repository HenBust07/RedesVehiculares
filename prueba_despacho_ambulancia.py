#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FASE 4.3
Accidente bus-moto, despacho, atención y retorno de ambulancia.

Requisitos:
    cuenca_reto.sumocfg
    hospitales.py
    vtypes.add.xml
    autos.rou.xml
    buses.rou.xml
    motos.rou.xml

Ejecución:
    python3 prueba_despacho_ambulancia.py --gui

La llegada se confirma al finalizar la ruta.
Durante los 120 segundos de atención, la ambulancia permanece
ocupada lógicamente, fuera de la red vial.

Posteriormente se reinserta para simular su retorno.
"""

import argparse
import os
import random
import sys

from collections import deque
from pathlib import Path


# ============================================================
# 0. CONFIGURACIÓN
# ============================================================

SUMO_HOME = os.environ.get("SUMO_HOME", "/usr/share/sumo")
sys.path.insert(0, str(Path(SUMO_HOME) / "tools"))

import traci
import sumolib

from hospitales import HOSPITALES


BASE = Path(__file__).resolve().parent
CFG = BASE / "cuenca_reto.sumocfg"

TIEMPO_EVENTO = 402

ID_BUS = "bus1"
ID_MOTO = "moto_accidente_01"

DISTANCIA_MOTO = 45.0
VELOCIDAD_MOTO = 28.0

PROB_RECHAZO = 0.25
SEMILLA = 42

MAX_ESPERA_COLISION = 60
MAX_ESPERA_AMBULANCIA = 1800

TIEMPO_ATENCION = 120

MAX_ESPERA_RETORNO = 1800


# ============================================================
# 1. FLOTA DE AMBULANCIAS
# ============================================================

def flota_inicial():

    asignacion = {
        "VCM": ["U01", "U02", "U03"],
        "IESS_JCA": ["U04"],
        "MILITAR": ["U05"],
        "MUNI_PAT": ["U06", "U07", "U08"],
        "MUNI_VALLE": ["U09", "U10"],
        "MONTE_SINAI": [],
        "DEL_RIO": [],
    }

    return {
        hospital: deque(asignacion[hospital])
        for hospital in HOSPITALES
    }


# ============================================================
# 2. INICIAR SUMO
# ============================================================

def iniciar_sumo(gui):

    binario = sumolib.checkBinary(
        "sumo-gui" if gui else "sumo"
    )

    comando = [
        binario,
        "-c", str(CFG),

        "--no-step-log", "true",

        "--summary-output",
        str(BASE / "summary_despacho.xml"),

        "--tripinfo-output",
        str(BASE / "tripinfo_despacho.xml"),

        "--statistic-output",
        str(BASE / "stats_despacho.xml"),

        "--collision-output",
        str(BASE / "collisions_despacho.xml"),
    ]

    print("Iniciando SUMO con TraCI...")

    traci.start(comando)


# ============================================================
# 3. GENERAR ACCIDENTE BUS-MOTO
# ============================================================

def preparar_accidente():

    while traci.simulation.getTime() < TIEMPO_EVENTO:
        traci.simulationStep()

    vehiculos = set(traci.vehicle.getIDList())

    if ID_BUS not in vehiculos:
        raise RuntimeError(
            f"{ID_BUS} no está activo en t={TIEMPO_EVENTO}"
        )

    edge_bus = traci.vehicle.getRoadID(ID_BUS)
    lane_bus = traci.vehicle.getLaneIndex(ID_BUS)

    pos_bus = traci.vehicle.getLanePosition(ID_BUS)
    velocidad = traci.vehicle.getSpeed(ID_BUS)

    if edge_bus.startswith(":"):
        raise RuntimeError(
            "El autobús está en una intersección interna"
        )

    if pos_bus <= DISTANCIA_MOTO + 5:
        raise RuntimeError(
            "No existe suficiente espacio para insertar la moto"
        )

    print("\n=== AUTOBÚS SELECCIONADO ===")

    print(f"Bus: {ID_BUS}")
    print(f"Arista: {edge_bus}")
    print(f"Carril: {lane_bus}")
    print(f"Posición: {pos_bus:.1f} m")
    print(f"Velocidad: {velocidad:.1f} m/s")

    ruta_bus = list(
        traci.vehicle.getRoute(ID_BUS)
    )

    indice = traci.vehicle.getRouteIndex(ID_BUS)

    if indice < 0 or indice >= len(ruta_bus):
        raise RuntimeError(
            "No se pudo determinar la ruta del autobús"
        )

    ruta_restante = ruta_bus[indice:]

    if not ruta_restante or ruta_restante[0] != edge_bus:

        ruta_restante = [edge_bus] + [
            e for e in ruta_restante
            if e != edge_bus
        ]

    traci.route.add(
        "ruta_moto_despacho",
        ruta_restante
    )

    traci.vehicle.add(
        vehID=ID_MOTO,
        routeID="ruta_moto_despacho",
        typeID="DEFAULT_VEHTYPE",
        depart="now",
        departLane=str(lane_bus),
        departPos=str(pos_bus - DISTANCIA_MOTO),
        departSpeed="0",
    )

    # Configuración de la motocicleta

    traci.vehicle.setVehicleClass(
        ID_MOTO, "motorcycle"
    )

    traci.vehicle.setShapeClass(
        ID_MOTO, "motorcycle"
    )

    traci.vehicle.setSpeedMode(
        ID_MOTO, 0
    )

    traci.vehicle.setLaneChangeMode(
        ID_MOTO, 0
    )

    traci.vehicle.setLaneChangeMode(
        ID_BUS, 0
    )

    print(
        f"Motocicleta {ID_MOTO} insertada "
        f"{DISTANCIA_MOTO:.0f} m detrás del autobús"
    )

    ultima_arista = edge_bus

    # Esperar la colisión

    for _ in range(MAX_ESPERA_COLISION):

        if ID_MOTO in traci.vehicle.getIDList():

            traci.vehicle.setSpeed(
                ID_MOTO,
                VELOCIDAD_MOTO
            )

        traci.simulationStep()

        if ID_BUS in traci.vehicle.getIDList():

            edge = traci.vehicle.getRoadID(ID_BUS)

            if edge and not edge.startswith(":"):
                ultima_arista = edge

        colisiones = traci.simulation.getCollisions()

        for colision in colisiones:

            involucrados = {
                colision.collider,
                colision.victim
            }

            if {ID_BUS, ID_MOTO}.issubset(involucrados):

                instante = traci.simulation.getTime()

                print("\n=== COLISIÓN BUS-MOTO CONFIRMADA ===")

                print(f"Tiempo: {instante:.0f} s")

                print(f"Carril: {colision.lane}")

                print(
                    f"Posición: {colision.pos:.2f} m"
                )

                print(
                    f"Arista de aproximación: {ultima_arista}"
                )

                # Inmovilizar vehículos accidentados

                for vehiculo in (ID_BUS, ID_MOTO):

                    if vehiculo in traci.vehicle.getIDList():

                        traci.vehicle.setSpeedMode(
                            vehiculo, 0
                        )

                        traci.vehicle.setLaneChangeMode(
                            vehiculo, 0
                        )

                        traci.vehicle.setSpeed(
                            vehiculo, 0
                        )

                        traci.vehicle.setColor(
                            vehiculo,
                            (255, 0, 0, 255)
                        )

                return instante, ultima_arista

    raise RuntimeError(
        "No se detectó la colisión bus-moto"
    )


# ============================================================
# 4. MANTENER ACCIDENTADOS INMOVILIZADOS
# ============================================================

def mantener_accidentados():

    for vehiculo in (ID_BUS, ID_MOTO):

        if vehiculo in traci.vehicle.getIDList():

            traci.vehicle.setSpeedMode(
                vehiculo, 0
            )

            traci.vehicle.setSpeed(
                vehiculo, 0
            )


# ============================================================
# 5. SELECCIONAR AMBULANCIA
# ============================================================

def seleccionar_ambulancia(arista_accidente, flota):

    rng = random.Random(SEMILLA)

    candidatos = []

    print("\n=== HOSPITALES CANDIDATOS ===")

    print(
        f'{"Hospital":<15} '
        f'{"Libres":>7} '
        f'{"Tiempo (s)":>12} '
        f'{"Distancia (m)":>15}'
    )

    for nombre, hospital in HOSPITALES.items():

        try:

            ruta = traci.simulation.findRoute(
                hospital["edge"],
                arista_accidente,
                vType="ambulance"
            )

            if not ruta.edges or ruta.travelTime < 0:
                raise ValueError("Sin ruta")

            print(
                f"{nombre:<15} "
                f"{len(flota[nombre]):>7} "
                f"{ruta.travelTime:>12.1f} "
                f"{ruta.length:>15.1f}"
            )

            if flota[nombre]:

                candidatos.append(
                    (ruta.travelTime, nombre, ruta)
                )

        except Exception as error:

            print(
                f"{nombre:<15} SIN RUTA: {error}"
            )

    print(
        "\n=== INTENTOS DE ASIGNACIÓN "
        "(25 % DE RECHAZO) ==="
    )

    candidatos.sort(key=lambda x: x[0])

    for _, nombre, ruta in candidatos:

        if rng.random() < PROB_RECHAZO:

            print(f"{nombre}: rechaza")
            continue

        unidad = flota[nombre].popleft()

        print(
            f"{nombre}: acepta; unidad {unidad}"
        )

        return nombre, unidad, ruta

    raise RuntimeError(
        "No existe una ambulancia disponible y aceptada"
    )


# ============================================================
# 6. DESPACHAR AMBULANCIA
# ============================================================

def despachar_y_esperar(
    nombre_hospital,
    unidad,
    ruta,
    instante_accidente
):

    id_ruta = "ruta_despacho_" + unidad

    traci.route.add(
        id_ruta,
        list(ruta.edges)
    )

    traci.vehicle.add(
        vehID=unidad,
        routeID=id_ruta,
        typeID="ambulance",
        depart="now",
        departPos="0"
    )

    traci.vehicle.setColor(
        unidad,
        (0, 0, 255, 255)
    )

    salida = traci.simulation.getTime()

    destino = ruta.edges[-1]

    print("\n=== AMBULANCIA DESPACHADA ===")

    print(f"Unidad: {unidad}")

    print(f"Hospital origen: {nombre_hospital}")

    print(f"Destino: {destino}")

    print(f"Salida: t={salida:.0f} s")

    print(
        f"Tiempo estimado: {ruta.travelTime:.1f} s"
    )

    # Seguimiento de la ambulancia

    for paso in range(MAX_ESPERA_AMBULANCIA):

        mantener_accidentados()

        traci.simulationStep()

        tiempo = traci.simulation.getTime()

        # Llegada confirmada

        if unidad in traci.simulation.getArrivedIDList():

            print("\n=== LLEGADA CONFIRMADA ===")

            print(f"Unidad: {unidad}")

            print(f"Llegada: t={tiempo:.0f} s")

            print(
                "Tiempo real desde despacho: "
                f"{tiempo - salida:.1f} s"
            )

            print(
                "Tiempo desde accidente: "
                f"{tiempo - instante_accidente:.1f} s"
            )

            return tiempo, destino

        # Comprobar teletransporte

        if unidad in traci.simulation.getEndingTeleportIDList():

            print(
                f"ERROR: {unidad} terminó un teletransporte"
            )

            return None

        # Comprobar si la ambulancia está circulando

        if unidad not in traci.vehicle.getIDList():

            if paso % 120 == 0:

                print(
                    f"t={tiempo:.0f} s | "
                    f"{unidad}: pendiente de inserción"
                )

            continue

        # Mostrar seguimiento cada 120 segundos

        if int(tiempo - salida) % 120 == 0:

            edge = traci.vehicle.getRoadID(unidad)

            velocidad = traci.vehicle.getSpeed(unidad)

            print(
                f"t={tiempo:.0f} s | "
                f"{unidad}: {edge} | "
                f"{velocidad:.1f} m/s"
            )

    print(
        "No se confirmó la llegada de la ambulancia"
    )

    return None


# ============================================================
# 7. ATENCIÓN DEL ACCIDENTE Y RETORNO
# ============================================================

def atender_y_retornar(
    unidad,
    arista_accidente,
    flota
):

    inicio = traci.simulation.getTime()

    print("\n=== ATENCIÓN DEL ACCIDENTE ===")

    print(f"Ambulancia: {unidad}")

    print(f"Inicio: t={inicio:.0f} s")

    print(
        f"Duración de atención: {TIEMPO_ATENCION} s"
    )

    # La ambulancia ya terminó su ruta.
    # SUMO la retiró de la red.
    #
    # Durante este intervalo permanece ocupada
    # lógicamente y no puede recibir otra solicitud.

    for _ in range(TIEMPO_ATENCION):

        mantener_accidentados()

        traci.simulationStep()

    fin = traci.simulation.getTime()

    print("\n=== ATENCIÓN FINALIZADA ===")

    print(f"Ambulancia: {unidad}")

    print(f"Inicio: {inicio:.0f} s")

    print(f"Fin: {fin:.0f} s")

    print(
        f"Tiempo de atención: {fin - inicio:.0f} s"
    )

    # --------------------------------------------------------
    # 7.1. LIBERAR LA VÍA
    # --------------------------------------------------------

    print("\n=== LIBERACIÓN DE LA VÍA ===")

    for vehiculo in (ID_BUS, ID_MOTO):

        if vehiculo in traci.vehicle.getIDList():

            traci.vehicle.remove(vehiculo)

            print(
                f"Vehículo retirado: {vehiculo}"
            )

        else:

            print(
                f"Vehículo {vehiculo} ya no está activo"
            )

    # --------------------------------------------------------
    # 7.2. CALCULAR RUTAS DE RETORNO
    # --------------------------------------------------------

    print("\n=== HOSPITALES PARA RETORNO ===")

    candidatos = []

    for nombre, hospital in HOSPITALES.items():

        try:

            ruta = traci.simulation.findRoute(
                arista_accidente,
                hospital["edge"],
                vType="ambulance"
            )

            if not ruta.edges or ruta.travelTime < 0:
                raise ValueError("Sin ruta")

            candidatos.append(
                (ruta.travelTime, nombre, ruta)
            )

            print(
                f"{nombre:<15} "
                f"{ruta.travelTime:>8.1f} s | "
                f"{ruta.length:>9.1f} m"
            )

        except Exception as error:

            print(
                f"{nombre:<15} SIN RUTA: {error}"
            )

    if not candidatos:

        raise RuntimeError(
            "No existe ruta de retorno a ningún hospital"
        )

    # Seleccionar hospital con menor tiempo

    candidatos.sort(key=lambda x: x[0])

    tiempo_estimado, hospital_retorno, ruta = candidatos[0]

    print("\n=== HOSPITAL DE RETORNO SELECCIONADO ===")

    print(f"Hospital: {hospital_retorno}")

    print(
        f"Tiempo estimado: {tiempo_estimado:.1f} s"
    )

    # --------------------------------------------------------
    # 7.3. REINSERTAR AMBULANCIA
    # --------------------------------------------------------

    id_ruta = "ruta_retorno_" + unidad

    traci.route.add(
        id_ruta,
        list(ruta.edges)
    )

    traci.vehicle.add(
        vehID=unidad,
        routeID=id_ruta,
        typeID="ambulance",
        depart="now",
        departPos="0"
    )

    # Color celeste durante el retorno

    traci.vehicle.setColor(
        unidad,
        (0, 180, 255, 255)
    )

    salida = traci.simulation.getTime()

    print("\n=== RETORNO INICIADO ===")

    print(f"Ambulancia: {unidad}")

    print(f"Destino: {hospital_retorno}")

    print(f"Salida: t={salida:.0f} s")

    print(
        f"ETA: {ruta.travelTime:.1f} s"
    )

    # --------------------------------------------------------
    # 7.4. SEGUIMIENTO DEL RETORNO
    # --------------------------------------------------------

    for paso in range(MAX_ESPERA_RETORNO):

        traci.simulationStep()

        tiempo = traci.simulation.getTime()

        # Llegada al hospital

        if unidad in traci.simulation.getArrivedIDList():

            flota[hospital_retorno].append(unidad)

            print("\n=== RETORNO CONFIRMADO ===")

            print(f"Ambulancia: {unidad}")

            print(f"Hospital: {hospital_retorno}")

            print(f"Llegada: t={tiempo:.0f} s")

            print(
                "Tiempo real de retorno: "
                f"{tiempo - salida:.1f} s"
            )

            print(
                f"{unidad} vuelve a estar disponible"
            )

            # Mostrar flota actualizada

            print("\n=== FLOTA ACTUALIZADA ===")

            for hospital, cola in flota.items():

                unidades = ", ".join(cola)

                if not unidades:
                    unidades = "Ninguna"

                print(
                    f"{hospital:<15} "
                    f"{len(cola)} disponibles | "
                    f"{unidades}"
                )

            return True

        # Comprobar teletransporte

        if unidad in traci.simulation.getEndingTeleportIDList():

            print(
                f"ERROR: {unidad} terminó un teletransporte"
            )

            return False

        # Mostrar seguimiento cada 120 pasos

        if paso % 120 == 0:

            if unidad in traci.vehicle.getIDList():

                edge = traci.vehicle.getRoadID(unidad)

                velocidad = traci.vehicle.getSpeed(unidad)

                print(
                    f"t={tiempo:.0f} s | "
                    f"{unidad}: {edge} | "
                    f"{velocidad:.1f} m/s"
                )

            else:

                print(
                    f"t={tiempo:.0f} s | "
                    f"{unidad}: pendiente de inserción"
                )

    print(
        "ERROR: no se confirmó el retorno"
    )

    return False


# ============================================================
# 8. PROGRAMA PRINCIPAL
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--gui",
        action="store_true",
        help="Mostrar simulación en SUMO-GUI"
    )

    args = parser.parse_args()

    if not CFG.exists():

        raise FileNotFoundError(
            f"No existe el archivo {CFG}"
        )

    iniciar_sumo(args.gui)

    try:

        # 1. Generar accidente

        instante, arista = preparar_accidente()

        # 2. Inicializar flota

        flota = flota_inicial()

        # 3. Seleccionar ambulancia

        hospital, unidad, ruta = seleccionar_ambulancia(
            arista,
            flota
        )

        # 4. Despachar ambulancia

        llegada = despachar_y_esperar(
            hospital,
            unidad,
            ruta,
            instante
        )

        # 5. Atención y retorno

        if llegada is not None:

            atender_y_retornar(
                unidad,
                llegada[1],
                flota
            )

        else:

            print(
                "No se inicia atención ni retorno "
                "porque la llegada no fue confirmada"
            )

        # Mantener SUMO-GUI abierto

        if args.gui:

            try:

                input(
                    "\nPresiona ENTER para cerrar SUMO-GUI..."
                )

            except (KeyboardInterrupt, EOFError):

                print("\nCerrando simulación...")

    finally:

        try:

            traci.close(False)

        except Exception as error:

            print(
                f"Aviso al cerrar TraCI: {error}"
            )


# ============================================================
# 9. EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
