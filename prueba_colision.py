import traci

# ==========================================================
# CONFIGURACIÓN
# ==========================================================

CONFIG = "cuenca_reto.sumocfg"

TIEMPO_ACCIDENTE = 402

ID_BUS = "bus1"
ID_MOTO = "moto_accidente_01"

DISTANCIA_DETRAS = 45.0
VELOCIDAD_MOTO = 28.0

TIEMPO_OBSERVACION = 60
TIEMPO_INMOVILIZACION = 120


# ==========================================================
# INICIAR SUMO-GUI
# ==========================================================

traci.start([
    "sumo-gui",
    "-c", CONFIG,
    "--no-step-log",
    "--no-warnings", "true"
])

try:

    print("\n=== INICIANDO SIMULACIÓN ===")

    # Avanzar hasta el segundo 402
    while traci.simulation.getTime() < TIEMPO_ACCIDENTE:
        traci.simulationStep()

    # ======================================================
    # VERIFICAR BUS
    # ======================================================

    if ID_BUS not in traci.vehicle.getIDList():
        raise RuntimeError(
            f"El bus {ID_BUS} no está activo."
        )

    edge_bus = traci.vehicle.getRoadID(ID_BUS)
    lane_bus = traci.vehicle.getLaneIndex(ID_BUS)
    pos_bus = traci.vehicle.getLanePosition(ID_BUS)

    pos_moto = pos_bus - DISTANCIA_DETRAS

    if pos_moto < 0:
        raise RuntimeError(
            "No existe espacio suficiente detrás del bus."
        )

    # ======================================================
    # OBTENER RUTA DEL BUS
    # ======================================================

    ruta_bus = traci.vehicle.getRoute(ID_BUS)

    indice_actual = traci.vehicle.getRouteIndex(ID_BUS)

    ruta_moto = ruta_bus[indice_actual:]

    if not ruta_moto:
        raise RuntimeError(
            "No se pudo obtener la ruta del bus."
        )

    # ======================================================
    # CREAR RUTA DE LA MOTOCICLETA
    # ======================================================

    traci.route.add(
        "ruta_moto_accidente_01",
        list(ruta_moto)
    )

    # ======================================================
    # INSERTAR MOTOCICLETA
    # ======================================================

    traci.vehicle.add(
        vehID=ID_MOTO,
        routeID="ruta_moto_accidente_01",
        typeID="DEFAULT_VEHTYPE",
        depart="now",
        departLane=str(lane_bus),
        departPos=str(pos_moto),
        departSpeed="0"
    )

    # Efectuar inserción
    traci.simulationStep()

    if ID_MOTO not in traci.vehicle.getIDList():
        raise RuntimeError(
            "La motocicleta no pudo insertarse."
        )

    # Configurar motocicleta
    traci.vehicle.setVehicleClass(
        ID_MOTO,
        "motorcycle"
    )

    traci.vehicle.setShapeClass(
        "moto_accidente_01", "motorcycle"
    )

    # Desactivar restricciones normales de seguridad
    traci.vehicle.setSpeedMode(ID_MOTO, 0)

    traci.vehicle.setLaneChangeMode(ID_MOTO, 0)

    # Restringir cambios de carril del bus
    traci.vehicle.setLaneChangeMode(ID_BUS, 0)

    print("\n=== PRUEBA DE COLISIÓN ===")

    print(f"Bus: {ID_BUS}")
    print(f"Motocicleta: {ID_MOTO}")

    print(
        f"Distancia inicial: "
        f"{DISTANCIA_DETRAS} m"
    )

    print(
        f"Velocidad objetivo de la moto: "
        f"{VELOCIDAD_MOTO} m/s"
    )

    # ======================================================
    # DETECTAR COLISIÓN
    # ======================================================

    colision_detectada = False

    for _ in range(TIEMPO_OBSERVACION):

        activos = traci.vehicle.getIDList()

        # Mantener velocidad de la motocicleta
        if ID_MOTO in activos:
            traci.vehicle.setSpeed(
                ID_MOTO,
                VELOCIDAD_MOTO
            )

        traci.simulationStep()

        tiempo = traci.simulation.getTime()

        # Mostrar diagnóstico cada cinco segundos
        if int(tiempo) % 5 == 0:

            activos = traci.vehicle.getIDList()

            if ID_BUS in activos and ID_MOTO in activos:

                velocidad_bus = traci.vehicle.getSpeed(
                    ID_BUS
                )

                velocidad_moto = traci.vehicle.getSpeed(
                    ID_MOTO
                )

                carril_bus = traci.vehicle.getLaneID(
                    ID_BUS
                )

                carril_moto = traci.vehicle.getLaneID(
                    ID_MOTO
                )

                distancia = traci.vehicle.getDrivingDistance(
                    ID_MOTO,
                    traci.vehicle.getRoadID(ID_BUS),
                    traci.vehicle.getLanePosition(ID_BUS)
                )

                print(
                    f"t={tiempo:.0f}s | "
                    f"Bus={velocidad_bus:.1f} m/s | "
                    f"Moto={velocidad_moto:.1f} m/s | "
                    f"Distancia={distancia:.1f} m | "
                    f"Mismo carril={carril_bus == carril_moto}"
                )

        # Consultar colisiones detectadas
        colisiones = traci.simulation.getCollisions()

        for colision in colisiones:

            participantes = {
                colision.collider,
                colision.victim
            }

            if ID_BUS in participantes and ID_MOTO in participantes:

                colision_detectada = True

                print("\n=== COLISIÓN DETECTADA ===")

                print(f"Tiempo: {tiempo:.0f} s")
                print(f"Bus: {ID_BUS}")
                print(f"Motocicleta: {ID_MOTO}")

                print(
                    f"Carril: {colision.lane}"
                )

                print(
                    f"Posición: {colision.pos:.2f} m"
                )

                # ==========================================
                # INMOVILIZAR VEHÍCULOS
                # ==========================================

                for vehiculo in [ID_BUS, ID_MOTO]:

                    if vehiculo in traci.vehicle.getIDList():

                        traci.vehicle.setSpeedMode(
                            vehiculo,
                            0
                        )

                        traci.vehicle.setSpeed(
                            vehiculo,
                            0
                        )

                        traci.vehicle.setLaneChangeMode(
                            vehiculo,
                            0
                        )

                        traci.vehicle.setColor(
                            vehiculo,
                            (255, 0, 0, 255)
                        )

                print(
                    "\nVehículos accidentados inmovilizados."
                )

                break

        if colision_detectada:
            break

    # ======================================================
    # MANTENER ACCIDENTE DURANTE 120 SEGUNDOS
    # ======================================================

    if colision_detectada:

        print("\n=== ACCIDENTE ACTIVO ===")

        tiempo_inicio = traci.simulation.getTime()

        for _ in range(TIEMPO_INMOVILIZACION):

            activos = traci.vehicle.getIDList()

            for vehiculo in [ID_BUS, ID_MOTO]:

                if vehiculo in activos:

                    traci.vehicle.setSpeedMode(
                        vehiculo,
                        0
                    )

                    traci.vehicle.setSpeed(
                        vehiculo,
                        0
                    )

            traci.simulationStep()

        tiempo_final = traci.simulation.getTime()

        print(
            f"Inicio de inmovilización: "
            f"{tiempo_inicio:.0f} s"
        )

        print(
            f"Fin de observación: "
            f"{tiempo_final:.0f} s"
        )

        print(
            f"Duración: "
            f"{tiempo_final - tiempo_inicio:.0f} s"
        )

        # Mostrar velocidades finales
        print("\n=== ESTADO FINAL ===")

        activos = traci.vehicle.getIDList()

        for vehiculo in [ID_BUS, ID_MOTO]:

            if vehiculo in activos:

                velocidad = traci.vehicle.getSpeed(
                    vehiculo
                )

                print(
                    f"{vehiculo}: "
                    f"{velocidad:.2f} m/s"
                )

            else:

                print(
                    f"{vehiculo}: "
                    "ya no está en la simulación"
                )

    else:

        print(
            "\nNo se detectó una colisión "
            "durante el tiempo de observación."
        )

    # ======================================================
    # MANTENER SUMO-GUI ABIERTO
    # ======================================================

    print("\n=== SIMULACIÓN FINALIZADA ===")

    print(
        "Revisa el accidente en SUMO-GUI."
    )

    input(
        "\nPresiona ENTER para cerrar la simulación..."
    )

finally:

    traci.close()

print("\nPrueba finalizada.")
