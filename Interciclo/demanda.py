"""Demanda planificada en Docker; nunca genera pasajeros nuevos en Windows."""
import csv
from dataclasses import dataclass
from pathlib import Path

RUTA = Path(__file__).resolve().parent / 'demanda_pasajeros.csv'

@dataclass(frozen=True)
class Movimiento:
    tiempo: float
    bus: str
    parada: str
    antes: int
    bajan: int
    suben: int
    despues: int
    duracion_parada: float = 0.0
    bajan_previstos: int = 0
    suben_previstos: int = 0
    coincide_demanda: bool = False

class DemandaCSV:
    def __init__(self, ruta=RUTA):
        ruta = Path(ruta)
        if not ruta.exists():
            raise FileNotFoundError(f'Falta {ruta}. Copia el CSV generado en Docker.')
        self.movimientos = {}
        with ruta.open(newline='', encoding='utf-8-sig') as f:
            for fila in csv.DictReader(f):
                clave = (fila['bus'], fila['parada'])
                if clave in self.movimientos:
                    raise ValueError(f'Fila duplicada en demanda: {clave}')
                self.movimientos[clave] = {k: int(fila[k]) for k in ('antes', 'bajan', 'suben', 'despues')}
        if not self.movimientos:
            raise ValueError('La demanda CSV está vacía.')

    def previsto(self, bus, parada):
        return self.movimientos.get((bus, parada))
