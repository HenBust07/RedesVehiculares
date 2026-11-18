"""Excel: una hoja por corrida; conserva las hojas históricas existentes."""
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

ARCHIVO = Path(__file__).resolve().parent / 'historial_pasajeros.xlsx'
ENCABEZADOS = [
    'Tiempo SUMO (s)', 'Bus', 'Parada', 'Ocupación antes', 'Bajan',
    'Suben', 'Ocupación después', 'Ocupación (%)',
    'Duración parada (s)', 'Bajan previstos', 'Suben previstos',
    'Coincide con CSV', 'Movimiento acumulado (s)',
    'Paradas acumuladas (s)', 'Semáforos acumulados (s)',
    'Otras detenciones (s)',
]

class HistorialExcel:
    def __init__(self, ruta=ARCHIVO):
        self.ruta = Path(ruta)
        self.nombre_hoja = None

    def iniciar(self, semilla, capacidad):
        if self.nombre_hoja is not None:
            return
        ahora = datetime.now()
        if self.ruta.exists():
            libro = load_workbook(self.ruta)
        else:
            libro = Workbook()
            libro.active.title = 'Información'
            libro.active['A1'] = 'Historial de ¡Viene a full!!!'
            libro.active['A2'] = 'Las nuevas hojas contienen mediciones de SUMO mediante TraCI.'
            libro.active.column_dimensions['A'].width = 82
        base = ahora.strftime('%m-%d_%H-%M-%S')
        nombre = base
        indice = 2
        while nombre in libro.sheetnames:
            nombre = f'{base}_{indice}'
            indice += 1
        hoja = libro.create_sheet(nombre)
        self.nombre_hoja = nombre
        hoja['A1'] = 'Fecha y hora de inicio'
        hoja['B1'] = ahora
        hoja['B1'].number_format = 'yyyy-mm-dd hh:mm:ss'
        hoja['D1'] = 'Semilla'
        hoja['E1'] = semilla
        hoja['F1'] = 'Capacidad'
        hoja['G1'] = capacidad
        hoja['I1'] = 'Fuente: pasajeros SUMO + TraCI; dos puertas'
        for col, titulo in enumerate(ENCABEZADOS, 1):
            celda = hoja.cell(3, col, titulo)
            celda.fill = PatternFill('solid', fgColor='17365D')
            celda.font = Font(color='FFFFFF', bold=True)
            celda.alignment = Alignment(wrap_text=True)
        for col, ancho in enumerate([20, 16, 13, 21, 11, 11, 22, 17, 21, 18, 18, 18, 23, 23, 24, 23], 1):
            hoja.column_dimensions[get_column_letter(col)].width = ancho
        hoja.row_dimensions[3].height = 36
        hoja.freeze_panes = 'A4'
        hoja.auto_filter.ref = 'A3:P3'
        libro.save(self.ruta)

    def registrar(self, evento, capacidad, tiempos=None):
        if self.nombre_hoja is None:
            raise RuntimeError('Primero se debe iniciar el historial')
        tiempos = tiempos or {}
        libro = load_workbook(self.ruta)
        hoja = libro[self.nombre_hoja]
        hoja.append([
            evento.tiempo, evento.bus, evento.parada, evento.antes,
            evento.bajan, evento.suben, evento.despues,
            evento.despues / capacidad, evento.duracion_parada,
            evento.bajan_previstos, evento.suben_previstos,
            'Sí' if evento.coincide_demanda else 'No',
            tiempos.get('movimiento', 0.), tiempos.get('parada', 0.),
            tiempos.get('semaforo', 0.), tiempos.get('otras_detenciones', 0.),
        ])
        fila = hoja.max_row
        hoja.cell(fila, 8).number_format = '0.0%'
        if not evento.coincide_demanda:
            hoja.cell(fila, 12).font = Font(color='C00000', bold=True)
        hoja.auto_filter.ref = f'A3:P{fila}'
        try:
            libro.save(self.ruta)
        except PermissionError as exc:
            raise PermissionError('Cierra historial_pasajeros.xlsx en Excel antes de simular.') from exc
