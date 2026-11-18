# P5 WiFi Occupancy Lab V1

Laboratorio de escritorio del proyecto **App de uso de espacio en buses**, de
Redes Vehiculares y Heterogéneas, Universidad de Cuenca. Permite registrar y
comparar observaciones WiFi de una o dos sondas ESP32 en un mismo bus.

**Estado:** prototipo experimental. Un dispositivo WiFi detectado no equivale
a un pasajero. El estimador es **NO CALIBRADO** y no hay fusión entre sondas.

## Qué hace

- Interfaz Python/Tkinter con lectura serial independiente y gráficas Matplotlib.
- SENSOR_01 y SENSOR_02 pertenecen al mismo BUS_001; se pueden usar por separado.
- Configuración del experimento: duración, teléfonos, ubicación, distancia,
  condiciones WiFi/pantalla/actividad, aforo manual y observaciones.
- Por ventana: Probe Requests, direcciones únicas aproximadas, RSSI, canal,
  heap libre y descartes. Canal fijo 6 de 2,4 GHz; UART a 115200 baudios.
- Inicio manual, pausa, reanudación, parada, historial y exportación CSV/PNG.
- Guardado incremental CSV/JSONL/metadatos. Ante corrupción serial, ventanas
  faltantes, duplicados, reinicios o desconexión, aborta y conserva datos válidos.
- Modelo opcional por sonda: `N = max(0, (D - B) / pd)`, con `B >= 0` y
  `0 < pd <= 1`. No tiene parámetros calibrados predeterminados.
- Modo demostración y pruebas con datos artificiales, sin abrir COM físicos.

## Contenido del repositorio

```text
captura/                 Interfaz modular y manual de uso
config/devices.json      Dos sondas, bus compartido e identidad serial esperada
firmware/esp32_sniffer/   Fuentes ESP-IDF y configuraciones de ambas sondas
tests/                   Pruebas artificiales de adquisición e integridad
docs/                    Diagrama y texto descriptivo para el informe
iniciar_laboratorio.ps1   Lanzador Windows; no instala dependencias
requirements-lab.txt     Versiones de bibliotecas usadas en el entorno original
MANIFEST.sha256          Huellas de los archivos distribuidos
```

No contiene SDK, compiladores, entornos virtuales, binarios, capturas, datos
reales ni registros seriales. Los datos se generan localmente al ejecutar.
Los directorios vacíos necesarios se crean al guardar cada experimento.

## Requisitos y puesta en marcha

Entorno de interfaz verificado en el proyecto original: Windows, Python
**3.14.3**, Tkinter **8.6**, PySerial **3.5**, Matplotlib **3.10.8** y NumPy
**2.4.4**. Tkinter pertenece a la instalación de Python; no se instala con pip.
ESP-IDF solo es necesario para compilar/programar las sondas, no para abrir la GUI.
No se han validado otros sistemas operativos o versiones de Python.

Extraiga el ZIP, entre a la carpeta y seleccione un Python que ya tenga esas
dependencias. El lanzador no cambia PATH global ni instala paquetes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -PythonPath 'C:\ruta\python.exe' -Diagnostico
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -PythonPath 'C:\ruta\python.exe' -Demo
```

Si `python` ya apunta al intérprete correcto puede omitir `-PythonPath`.
Para preparar un equipo nuevo, instale Python y las dependencias únicamente
con autorización del responsable. Fuentes oficiales: [Python](https://www.python.org/),
[PySerial](https://pypi.org/project/pyserial/),
[Matplotlib](https://pypi.org/project/matplotlib/) y
[NumPy](https://pypi.org/project/numpy/). Este paquete no las incluye.
Comando opcional para un entorno ya elegido, **no ejecutado al abrir la aplicación**:

```powershell
python -m pip install --no-cache-dir -r requirements-lab.txt
```

Mantenga al menos 1 GB libre; el almacenamiento de observaciones exige 1,5 GB
preventivos en las unidades comprobadas. No duplique instalaciones de ESP-IDF.

## Preparar el hardware si aún no tiene el firmware

Configuración original: SENSOR_01, ESP32-D0WD revisión 1.0 con CH340; SENSOR_02,
ESP32-D0WD-V3 revisión 3.1 con CP210x. Ambas con 4 MiB de flash, target `esp32`.
La selección/verificación USB actual espera CH340 para SENSOR_01 y CP210x para
SENSOR_02; otras combinaciones de puentes USB requieren adaptar y validar esa
comprobación, no simplemente cambiar un COM en el inventario.

Reutilice ESP-IDF **v5.5.6** y su toolchain para `esp32`. Si no está disponible,
prepare el entorno por el procedimiento [oficial de Espressif](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32/get-started/index.html),
con autorización y espacio suficiente. No se incluye el SDK.
En una terminal que ya tenga exportado ESP-IDF, desde la raíz del proyecto:

```powershell
Set-Location firmware\esp32_sniffer
$env:CCACHE_DISABLE = '1'
$env:IDF_CCACHE_ENABLE = '0'
$env:IDF_COMPONENT_MANAGER = '0'
# SENSOR_01: identificador serial heredado BUS_001
idf.py -B build -D SDKCONFIG=sdkconfig build
# SENSOR_02: identificador serial heredado BUS_002
idf.py -B build_sensor02 -D SDKCONFIG=sdkconfig.sensor02 build
```

Las configuraciones incluidas ya seleccionan `esp32`; no es necesario ejecutar
`set-target`, que podría regenerarlas. No flashee una compilación fallida.
**Identifique físicamente cada placa y resuelva la preservación del firmware
anterior antes de programar.** Solo con autorización, sustituya COM_A/COM_B por
los puertos realmente verificados (no son números universales):

```powershell
idf.py -B build -D SDKCONFIG=sdkconfig -p COM_A flash
idf.py -B build_sensor02 -D SDKCONFIG=sdkconfig.sensor02 -p COM_B flash
Set-Location ..\..
```

Estos comandos no se ejecutan automáticamente. No use `erase-flash` ni escriba
eFuses. Al arrancar, la sonda ejecuta 19 autopruebas con radio apagada y espera
START. **BUS_002 en la salida del segundo firmware es un identificador serial
heredado, no otro bus**: la GUI lo presenta como SENSOR_02 dentro de BUS_001.

## Experimento controlado reproducible

1. Prepare dispositivos propios o participantes autorizados; documente las
   condiciones. El receptor también puede oír equipos externos dentro de alcance.
2. Ubique las sondas en el mismo bus o escenario de laboratorio y documente
   posiciones, distancia, cantidad de teléfonos y referencia manual real.
3. Abra la GUI sin `-Demo`, actualice puertos y seleccione cada placa correcta.
   Conecte una o ambas; espere las 19 autopruebas y el estado listo, radio OFF.
4. Seleccione una plantilla P0–P9 y complete la ficha. Son propuestas editables,
   no protocolos oficiales de la rúbrica. Para una prueba inicial use **120 s**:
   el firmware genera doce ventanas completas de **10 s** por START.
5. Registre aforo inicial y condiciones WiFi, pantalla y actividad. Si estima,
   justifique B y pd por sonda como supuestos, sin llamarlos calibrados; puede
   dejar la estimación deshabilitada para medir únicamente los agregados.
6. Confirme entorno autorizado y correspondencia física; pulse **Iniciar**.
   La identidad serial se verifica al primer JSON; antes solo se conoce la
   identidad esperada. No se inicia radio para descubrir puertos.
7. Actualice el aforo manual cuando cambie y registre notas. No añada MAC, SSID
   ni datos personales. La pausa exige STOP confirmado; la reanudación abre un
   segmento nuevo. No hay captura automática al iniciar la aplicación.
8. Espere el fin o pulse **Detener y cerrar**. Compruebe parada, cierre de
   puertos y ausencia de incidencias antes de considerar el ensayo válido.
9. Consulte historial y exporte resultados. Informe fallos, condiciones y
   limitaciones; no mezcle ensayos abortados con los aprobados.

## Datos y límites de interpretación

Reales: `data/raw/p5_lab/`; artificiales: `data/synthetic/p5_lab/`.
Cada experimento conserva condiciones, parámetros y tiempos. Los campos
`bus_id` y `probe_id` separan bus y sonda; `sensor_id` conserva el ID serial
heredado. El reloj monotónico PC permite comparación temporal aproximada,
sin sincronización exacta de ventanas entre placas. El aforo manual es una
referencia observada, no un resultado del sniffer.

No sume direcciones únicas entre sondas ni ventanas. MAC aleatorias, teléfonos
silenciosos, múltiples dispositivos por persona y equipos externos afectan el
conteo. Cero detecciones no prueba ausencia de personas. La aplicación no mide
las pérdidas internas del driver ni garantiza captura sin pérdidas. Los errores
seriales intermitentes históricos requieren verificar integridad en cada ensayo.
No hay calibración de ocupación validada, AP privado, salto de canales,
filtrado de dispositivos fijos, backend ni aplicación de pasajeros.

La salida solo contiene agregados: no se almacenan MAC originales, SSID ni
contenido de tramas. No publique los datos reales por defecto; revise
manualmente cualquier archivo que pretenda compartir.

## Pruebas sin hardware

Desde la raíz y con el Python que tiene las dependencias:

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_p5_lab.py -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -PruebaInterfaz
```

Las pruebas usan transportes ficticios, no COM físicos ni radio. Incluyen
lectura simultánea, corrupción, ventanas faltantes, reinicios, pausas y cierre
de puertos. Sus resultados son evidencia de software, no de precisión de aforo
ni de recepción inalámbrica real. La validación del contenido extraído del ZIP
se registra por separado junto al paquete de distribución original.

Manual completo: [captura/MANUAL_LABORATORIO.md](captura/MANUAL_LABORATORIO.md).
Diagrama y descripción: [docs/interfaz_laboratorio_informe.md](docs/interfaz_laboratorio_informe.md).

## Subir a GitHub

Extraiga el ZIP y suba **los archivos y carpetas de su interior**, con README.md
en la raíz del repositorio, para que GitHub muestre esta descripción. Puede
adjuntar el ZIP a una Release; subir solo el ZIP no permite explorar el código
ni muestra su README como portada. Revise los archivos antes de publicar.
No se asigna una licencia de distribución en este paquete: el titular debe
elegirla antes de autorizar usos o redistribuciones por terceros.
