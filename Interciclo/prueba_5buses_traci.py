
import traci

HOST = "127.0.0.1"
PUERTO = 3400

print("Conectando con SUMO...")

traci.init(
    host=HOST,
    port=PUERTO,
    numRetries=5
)

print("Conexion establecida.")

try:
    while traci.simulation.getTime() < 600:

        traci.simulationStep()

        tiempo = traci.simulation.getTime()
        buses = traci.vehicle.getIDList()

        if int(tiempo) % 10 == 0:

            print(f"\nTiempo SUMO: {tiempo:.0f} s")
            print(f"Buses activos: {len(buses)}")

            for bus in buses:

                x, y = traci.vehicle.getPosition(bus)
                velocidad = traci.vehicle.getSpeed(bus)

                print(
                    f"{bus} | "
                    f"X={x:.1f} | "
                    f"Y={y:.1f} | "
                    f"Velocidad={velocidad:.1f} m/s"
                )

finally:
    traci.close()
    print("\nConexion TraCI cerrada.")
