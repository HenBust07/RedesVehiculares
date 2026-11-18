"""Genera variante de dos puertas con tiempos de parada cortos.
Se ejecuta en Docker, en la carpeta donde están los XML y el CSV.
"""
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

SEGUNDOS_POR_PERSONA = 1.5  # ajustar según observaciones reales
TIEMPO_AUXILIAR = 1.0      # P0/P4: paradas técnicas, no se muestran

base = Path('linea3_buses_dos_puertas.rou.xml')
if not base.exists():
    raise SystemExit(f'No existe {base}')
with open('demanda_pasajeros.csv', newline='', encoding='utf-8') as f:
    demanda = {(r['bus'], r['parada']): r for r in csv.DictReader(f)}

tree = ET.parse(base)
root = tree.getroot()
tipo = root.find("./vType[@id='bus_linea3']")
if tipo is None:
    raise SystemExit('No existe bus_linea3')
tipo.set('boardingDuration', '0')
tipo.set('loadingDuration', '0')
for bus in root.findall('vehicle'):
    bus_id = bus.get('id')
    for stop in bus.findall('stop'):
        parada = stop.get('busStop')
        if parada in ('P0', 'P4'):
            duracion = TIEMPO_AUXILIAR
        else:
            r = demanda[(bus_id, parada)]
            duracion = SEGUNDOS_POR_PERSONA * max(int(r['suben']), int(r['bajan']))
        stop.set('duration', f'{duracion:g}')
        stop.attrib.pop('extension', None)
        print(f'{bus_id} {parada}: {duracion:g} s')

ET.indent(tree, space='    ')
salida = 'linea3_buses_dos_puertas_rapido.rou.xml'
tree.write(salida, encoding='utf-8', xml_declaration=True)
print('Generado:', salida)
