#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FASE 4.2: accidente bus-moto y despacho REAL de una ambulancia.

Requisitos en la misma carpeta:
  cuenca_reto.sumocfg, hospitales.py, vtypes.add.xml y rutas de tráfico.
El .sumocfg NO debe contener <traci_server><remote-port .../>.

Uso:
  python3 prueba_despacho_ambulancia.py --gui
  python3 prueba_despacho_ambulancia.py

Esta versión termina al confirmar llegada de la ambulancia. No implementa
los 120 s de atención ni el retorno al hospital (siguiente validación).
"""

# ============================================================================
# PARTE 0. IMPORTACIONES Y CONFIGURACIÓN
# ============================================================================
import argparse
import os
import random
import sys
from collections import deque
from pathlib import Path

SUMO_HOME = os.environ.get('SUMO_HOME', '/usr/share/sumo')
sys.path.insert(0, str(Path(SUMO_HOME) / 'tools'))
import traci
import sumolib
from hospitales import HOSPITALES

BASE = Path(__file__).resolve().parent
CFG = BASE / 'cuenca_reto.sumocfg'
TIEMPO_EVENTO = 402
ID_BUS = 'bus1'
ID_MOTO = 'moto_accidente_01'
DISTANCIA_MOTO = 45.0
VELOCIDAD_MOTO = 28.0
PROB_RECHAZO = 0.25
SEMILLA = 42
MAX_ESPERA_COLISION = 60
MAX_ESPERA_AMBULANCIA = 1800


def flota_inicial():
    """Misma flota verificada en la fase 2."""
    asignacion = {
        'VCM': ['U01', 'U02', 'U03'],
        'IESS_JCA': ['U04'],
        'MILITAR': ['U05'],
        'MUNI_PAT': ['U06', 'U07', 'U08'],
        'MUNI_VALLE': ['U09', 'U10'],
        'MONTE_SINAI': [],
        'DEL_RIO': [],
    }
    return {h: deque(asignacion[h]) for h in HOSPITALES}


def iniciar_sumo(gui):
    binario = sumolib.checkBinary('sumo-gui' if gui else 'sumo')
    cmd = [
        binario, '-c', str(CFG),
        '--no-step-log', 'true',
        '--summary-output', str(BASE / 'summary_despacho.xml'),
        '--tripinfo-output', str(BASE / 'tripinfo_despacho.xml'),
        '--statistic-output', str(BASE / 'stats_despacho.xml'),
        '--collision-output', str(BASE / 'collisions_despacho.xml'),
    ]
    print('Iniciando SUMO con TraCI...', flush=True)
    traci.start(cmd)


# ============================================================================
# PARTE 1. REPRODUCIR EL ACCIDENTE BUS-MOTO (FASE 3)
# ============================================================================
def preparar_accidente():
    while traci.simulation.getTime() < TIEMPO_EVENTO:
        traci.simulationStep()

    ids = set(traci.vehicle.getIDList())
    if ID_BUS not in ids:
        raise RuntimeError(f'{ID_BUS} no está activo en t={TIEMPO_EVENTO}. '
                           'Verifica que usas las mismas rutas de la fase 3.')

    edge_bus = traci.vehicle.getRoadID(ID_BUS)
    lane_bus = traci.vehicle.getLaneIndex(ID_BUS)
    pos_bus = traci.vehicle.getLanePosition(ID_BUS)
    velocidad = traci.vehicle.getSpeed(ID_BUS)
    if edge_bus.startswith(':') or pos_bus <= DISTANCIA_MOTO + 5:
        raise RuntimeError(f'{ID_BUS} no está en posición adecuada: '
                           f'arista={edge_bus}, pos={pos_bus:.1f} m')
    print(f'Bus: {ID_BUS}, arista={edge_bus}, carril={lane_bus}, '
          f'pos={pos_bus:.1f} m, velocidad={velocidad:.1f} m/s')

    ruta_bus = list(traci.vehicle.getRoute(ID_BUS))
    indice = traci.vehicle.getRouteIndex(ID_BUS)
    if indice < 0 or indice >= len(ruta_bus):
        raise RuntimeError('No se pudo determinar la ruta restante del autobús.')
    ruta_restante = ruta_bus[indice:]
    if not ruta_restante or ruta_restante[0] != edge_bus:
        ruta_restante = [edge_bus] + [e for e in ruta_restante if e != edge_bus]

    traci.route.add('ruta_moto_despacho', ruta_restante)
    traci.vehicle.add(
        vehID=ID_MOTO,
        routeID='ruta_moto_despacho',
        typeID='DEFAULT_VEHTYPE',
        depart='now',
        departLane=str(lane_bus),
        departPos=str(pos_bus - DISTANCIA_MOTO),
        departSpeed='0',
    )
    # La clase de circulación y la forma gráfica son propiedades distintas.
    traci.vehicle.setVehicleClass(ID_MOTO, 'motorcycle')
    traci.vehicle.setShapeClass(ID_MOTO, 'motorcycle')
    traci.vehicle.setSpeedMode(ID_MOTO, 0)
    traci.vehicle.setLaneChangeMode(ID_MOTO, 0)
    traci.vehicle.setLaneChangeMode(ID_BUS, 0)
    print(f'Motocicleta {ID_MOTO} insertada 45 m detrás de {ID_BUS}.')

    ultima_arista = edge_bus
    for _ in range(MAX_ESPERA_COLISION):
        if ID_MOTO in traci.vehicle.getIDList():
            traci.vehicle.setSpeed(ID_MOTO, VELOCIDAD_MOTO)
        traci.simulationStep()
        if ID_BUS in traci.vehicle.getIDList():
            e = traci.vehicle.getRoadID(ID_BUS)
            if e and not e.startswith(':'):
                ultima_arista = e
        for choque in traci.simulation.getCollisions():
            involucrados = {choque.collider, choque.victim}
            if {ID_BUS, ID_MOTO}.issubset(involucrados):
                instante = traci.simulation.getTime()
                print('\n=== COLISIÓN BUS–MOTO CONFIRMADA ===')
                print(f'Tiempo: {instante:.0f} s')
                print(f'Carril: {choque.lane}; posición: {choque.pos:.2f} m')
                print(f'Arista de aproximación: {ultima_arista}')
                for veh in (ID_BUS, ID_MOTO):
                    if veh in traci.vehicle.getIDList():
                        traci.vehicle.setSpeedMode(veh, 0)
                        traci.vehicle.setLaneChangeMode(veh, 0)
                        traci.vehicle.setSpeed(veh, 0)
                        traci.vehicle.setColor(veh, (255, 0, 0, 255))
                return instante, ultima_arista
    raise RuntimeError('No se detectó la colisión bus–moto dentro de 60 s.')


def mantener_accidentados():
    for veh in (ID_BUS, ID_MOTO):
        if veh in traci.vehicle.getIDList():
            traci.vehicle.setSpeedMode(veh, 0)
            traci.vehicle.setSpeed(veh, 0)


# ============================================================================
# PARTE 2. ELEGIR HOSPITAL Y APLICAR RECHAZO DEL 25 %
# ============================================================================
def seleccionar_ambulancia(arista_accidente, flota):
    rng = random.Random(SEMILLA)
    candidatos = []
    print('\n=== HOSPITALES CANDIDATOS ===')
    print(f'{"Hospital":<15} {"Libres":>7} {"Tiempo (s)":>12} {"Distancia (m)":>15}')
    for nombre, hospital in HOSPITALES.items():
        try:
            ruta = traci.simulation.findRoute(
                hospital['edge'], arista_accidente, vType='ambulance')
            if not ruta.edges or ruta.travelTime < 0:
                raise ValueError('sin ruta')
            print(f'{nombre:<15} {len(flota[nombre]):>7} '
                  f'{ruta.travelTime:>12.1f} {ruta.length:>15.1f}')
            if flota[nombre]:
                candidatos.append((ruta.travelTime, nombre, ruta))
        except Exception as exc:
            print(f'{nombre:<15} SIN RUTA: {exc}')

    print('\n=== INTENTOS DE ASIGNACIÓN (25 % DE RECHAZO) ===')
    for _, nombre, ruta in sorted(candidatos, key=lambda x: x[0]):
        if rng.random() < PROB_RECHAZO:
            print(f'{nombre}: rechaza')
            continue
        unidad = flota[nombre].popleft()
        print(f'{nombre}: acepta; unidad {unidad}')
        return nombre, unidad, ruta
    raise RuntimeError('No hay hospitales con ruta, ambulancia y aceptación.')


# ============================================================================
# PARTE 3. DESPACHO REAL Y COMPROBACIÓN DE LLEGADA
# ============================================================================
def despachar_y_esperar(nombre_hospital, unidad, ruta, instante_accidente):
    route_id = 'ruta_despacho_' + unidad
    traci.route.add(route_id, list(ruta.edges))
    traci.vehicle.add(
        vehID=unidad,
        routeID=route_id,
        typeID='ambulance',
        depart='now',
        departPos='0',
    )
    traci.vehicle.setColor(unidad, (0, 0, 255, 255))
    salida = traci.simulation.getTime()
    destino = ruta.edges[-1]
    print('\n=== AMBULANCIA DESPACHADA ===')
    print(f'Unidad: {unidad}; origen: {nombre_hospital}; destino: {destino}')
    print(f'Salida: t={salida:.0f} s; ETA ruta: {ruta.travelTime:.1f} s')

    # En esta primera validación, llegar al final de la ruta se toma como
    # llegada a la arista de aproximación, no al punto exacto del choque.
    for paso in range(MAX_ESPERA_AMBULANCIA):
        mantener_accidentados()
        traci.simulationStep()
        tiempo = traci.simulation.getTime()
        if unidad in traci.simulation.getArrivedIDList():
            print('\n=== LLEGADA CONFIRMADA ===')
            print(f'Unidad: {unidad}; llegada t={tiempo:.0f} s')
            print(f'Tiempo real desde despacho: {tiempo - salida:.1f} s')
            print(f'Tiempo desde accidente: {tiempo - instante_accidente:.1f} s')
            print('Estado: llegada a la arista de aproximación (fin de ruta).')
            return True
        if unidad in traci.simulation.getEndingTeleportIDList():
            print(f'AVISO: {unidad} terminó un teleport; no se considera llegada válida.')
            return False
        if unidad not in traci.vehicle.getIDList():
            # Puede estar pendiente de inserción; esperar en lugar de declarar
            # una falsa llegada o un fallo prematuro.
            if paso % 120 == 0:
                print(f'  t={tiempo:.0f} s | {unidad}: pendiente de inserción')
            continue
        if int(tiempo - salida) % 120 == 0:
            print(f'  t={tiempo:.0f} s | {unidad}: '
                  f'{traci.vehicle.getRoadID(unidad)} | '
                  f'{traci.vehicle.getSpeed(unidad):.1f} m/s')
    print('No se confirmó la llegada dentro del tiempo máximo de espera.')
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true', help='Mostrar SUMO-GUI por VNC')
    args = parser.parse_args()
    if not CFG.exists():
        raise FileNotFoundError(f'No existe {CFG}')
    iniciar_sumo(args.gui)
    try:
        instante, arista = preparar_accidente()
        flota = flota_inicial()
        nombre, unidad, ruta = seleccionar_ambulancia(arista, flota)
        despachar_y_esperar(nombre, unidad, ruta, instante)
        if args.gui:
            try:
                input('\nENTER para cerrar SUMO-GUI... ')
            except (KeyboardInterrupt, EOFError):
                print('\nCerrando sin esperar a SUMO-GUI...')
    finally:
        # Evita que el cierre de la GUI bloquee la terminal.
        try:
            traci.close(False)
        except Exception as exc:
            print(f'Aviso al cerrar TraCI: {exc}')


if __name__ == '__main__':
    main()
