"""TraCI: ocupación real de SUMO y tiempos clasificados por bus."""
from collections import defaultdict
import traci
from configuracion import HOST, PUERTO, PARADAS, CAPACIDAD_BUS, VELOCIDAD_ETA_M_S
from demanda import DemandaCSV, Movimiento
from historial import HistorialExcel

PARADAS_AUXILIARES = {'P0', 'P4'}
DISTANCIA_VISIBLE_DESPUES_P3 = 100.0  # metros recorridos sobre la ruta

class Simulacion:
    def __init__(self):
        self.conectada = False
        self.terminada = False
        self.tiempo = 0.0
        self.buses = []
        self.demanda = DemandaCSV()
        self.historial = HistorialExcel()
        self.eventos_recientes = []
        self.atendidas = set()
        self.en_parada = {}
        self.pasajeros_previos = {}
        self.ultimos_pendientes = {}
        self.tiempos = defaultdict(lambda: {'movimiento': 0., 'parada': 0., 'semaforo': 0., 'otras_detenciones': 0.})
        self.avisos = []
        self.distancia_salida_p3 = {}

    def conectar(self):
        if self.conectada:
            return
        traci.init(host=HOST, port=PUERTO, numRetries=3)
        self.conectada = True
        self.terminada = False
        self.tiempo = traci.simulation.getTime()
        self.historial.iniciar(2026, CAPACIDAD_BUS)
        self._leer_buses(0.)

    def _paradas_pendientes(self, bus_id):
        try:
            stops = traci.vehicle.getStops(bus_id)
            ids = [getattr(s, 'stoppingPlaceID', '') for s in stops]
        except (AttributeError, traci.TraCIException):
            stops = traci.vehicle.getNextStops(bus_id)
            ids = [s[2] for s in stops]
        return list(dict.fromkeys(p for p in ids if p in PARADAS))

    def _parada_actual(self, bus_id):
        """getNextStops mantiene el busStop actual durante la detención."""
        if not traci.vehicle.isStopped(bus_id):
            return None
        try:
            stops = traci.vehicle.getNextStops(bus_id)
            if stops:
                nombre = stops[0][2]
                if nombre in PARADAS or nombre in PARADAS_AUXILIARES:
                    return nombre
        except (traci.TraCIException, IndexError, TypeError):
            pass
        # Respaldo para versiones de TraCI donde getNextStops omite la parada actual.
        try:
            if traci.vehicle.getStopState(bus_id) == 0:
                return None
            edge = traci.vehicle.getRoadID(bus_id)
            pos = traci.vehicle.getLanePosition(bus_id)
            for parada, objetivo in PARADAS.items():
                if edge == objetivo['edge'] and abs(pos - objetivo['pos']) <= 20:
                    return parada
        except (AttributeError, traci.TraCIException):
            pass
        return None

    def _eta(self, bus_id, parada):
        try:
            d = PARADAS[parada]
            distancia = traci.vehicle.getDrivingDistance(bus_id, d['edge'], d['pos'])
            return max(0., distancia / VELOCIDAD_ETA_M_S / 60.) if distancia >= 0 else None
        except traci.TraCIException:
            return None

    def _clasificar(self, bus_id, parada, dt):
        if dt <= 0:
            return
        t = self.tiempos[bus_id]
        if parada is not None:
            t['parada'] += dt
            return
        velocidad = traci.vehicle.getSpeed(bus_id)
        if velocidad > 0.1:
            t['movimiento'] += dt
            return
        try:
            semaforos = traci.vehicle.getNextTLS(bus_id)
            # Solo clasificar como semáforo si está próximo y restringe el paso.
            if any(0 <= s[2] <= 25 and s[3].lower() in ('r', 'y') for s in semaforos):
                t['semaforo'] += dt
                return
        except (AttributeError, traci.TraCIException):
            pass
        t['otras_detenciones'] += dt

    def _cerrar_parada(self, bus_id, parada, estado, pasajeros_actuales):
        clave = (bus_id, parada)
        if clave in self.atendidas:
            return
        self.atendidas.add(clave)
        inicial = estado['inicial']
        final = set(pasajeros_actuales)
        suben = len(final - inicial)
        bajan = len(inicial - final)
        antes = len(inicial)
        despues = len(final)
        previsto = self.demanda.previsto(bus_id, parada)
        coincide = bool(previsto and (previsto['antes'], previsto['bajan'], previsto['suben'], previsto['despues']) == (antes, bajan, suben, despues))
        if not coincide:
            self.avisos.append(f'{bus_id} {parada}: movimiento real distinto del CSV')
        if parada in PARADAS:
            evento = Movimiento(self.tiempo, bus_id, parada, antes, bajan, suben, despues,
                                self.tiempo - estado['inicio'],
                                previsto['bajan'] if previsto else 0,
                                previsto['suben'] if previsto else 0, coincide)
            self.eventos_recientes.append(evento)
            self.historial.registrar(evento, CAPACIDAD_BUS, self.tiempos[bus_id])
            print(f'[t={self.tiempo:.0f}s] {bus_id} {parada}: '
                  f'bajan={bajan} suben={suben} ocupacion={despues}/50 '
                  f'detencion={evento.duracion_parada:.0f}s CSV={"OK" if coincide else "DIFIERE"}')

    def _leer_buses(self, dt):
        self.eventos_recientes = []
        resultado = []
        activos = set(traci.vehicle.getIDList())
        for bus_id in sorted(activos):
            if not bus_id.startswith('bus_'):
                continue
            pasajeros = set(traci.vehicle.getPersonIDList(bus_id))
            actual = self._parada_actual(bus_id)
            anterior = self.en_parada.get(bus_id)
            if anterior and actual != anterior['parada']:
                # En el primer paso después de salir, el intercambio ya terminó.
                self._cerrar_parada(bus_id, anterior['parada'], anterior, pasajeros)
                if anterior['parada'] == 'P3':
                    self.distancia_salida_p3[bus_id] = traci.vehicle.getDistance(bus_id)
                self.en_parada.pop(bus_id, None)
            if actual and bus_id not in self.en_parada:
                self.en_parada[bus_id] = {
                    'parada': actual,
                    'inicio': self.tiempo - dt,
                    'inicial': set(self.pasajeros_previos.get(bus_id, set())),
                }
            self._clasificar(bus_id, actual, dt)
            self.pasajeros_previos[bus_id] = pasajeros
            pendientes = self._paradas_pendientes(bus_id)
            if actual in PARADAS and actual not in pendientes:
                pendientes.insert(0, actual)
            eta = {p: self._eta(bus_id, p) for p in pendientes}
            x, y = traci.vehicle.getPosition(bus_id)
            distancia_p3 = self.distancia_salida_p3.get(bus_id)
            visible_mapa = (
                (bus_id, 'P0') in self.atendidas
                and (distancia_p3 is None or
                     traci.vehicle.getDistance(bus_id) - distancia_p3 < DISTANCIA_VISIBLE_DESPUES_P3)
            )
            resultado.append({
                'id': bus_id, 'x': x, 'y': y,
                'velocidad': traci.vehicle.getSpeed(bus_id),
                'paradas_pendientes': pendientes, 'eta': eta,
                'ocupacion': len(pasajeros), 'capacidad_maxima': CAPACIDAD_BUS,
                'estado': 'En ' + actual if actual else 'Circulando',
                'visible_mapa': visible_mapa,
                'tiempos': dict(self.tiempos[bus_id]),
            })
        # Si el bus terminó su ruta justo después de P4, cerrar el último evento.
        for bus_id in list(self.en_parada):
            if bus_id not in activos:
                self.en_parada.pop(bus_id, None)
        self.buses = resultado

    def avanzar(self):
        if not self.conectada or self.terminada:
            return
        anterior = self.tiempo
        traci.simulationStep()
        self.tiempo = traci.simulation.getTime()
        self._leer_buses(max(0., self.tiempo - anterior))
        self.terminada = traci.simulation.getMinExpectedNumber() == 0

    def cerrar(self):
        if self.conectada:
            try:
                traci.close()
            finally:
                self.conectada = False
