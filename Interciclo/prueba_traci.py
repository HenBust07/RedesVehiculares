
import traci

HOST = "127.0.0.1"
PUERTO = 3400

print("Conectando con SUMO...")

try:
    traci.init(
        host=HOST,
        port=PUERTO,
        numRetries=5
    )

    print("Conexión TraCI establecida correctamente.")

    for paso in range(10):
        traci.simulationStep()

        tiempo = traci.simulation.getTime()
        vehiculos = traci.vehicle.getIDList()

        print(
            f"Tiempo: {tiempo:.1f} s | "
            f"Vehículos activos: {len(vehiculos)}"
        )

except Exception as e:
    print(f"Error de conexión o simulación: {e}")

finally:
    if traci.isLoaded():
        traci.close()
