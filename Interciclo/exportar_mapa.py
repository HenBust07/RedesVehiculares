"""Ejecutar DENTRO de Docker, junto a linea3_tramo.net.xml."""
import json
import sys
from pathlib import Path
sys.path.insert(0, '/usr/share/sumo/tools')
import sumolib

red = sumolib.net.readNet('linea3_tramo.net.xml')
calles = []
for edge in red.getEdges():
    if edge.getFunction() == 'internal':
        continue
    shape = edge.getShape()
    if len(shape) > 1:
        calles.append([[round(x, 2), round(y, 2)] for x, y in shape])
Path('mapa_linea3.json').write_text(
    json.dumps({'calles': calles}, ensure_ascii=False), encoding='utf-8'
)
print(f'Exportadas {len(calles)} geometrías a mapa_linea3.json')
