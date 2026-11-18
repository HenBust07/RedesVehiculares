# Redes Vehiculares y Heterogéneas

Repositorio colaborativo de prácticas y proyectos de la asignatura **Redes
Vehiculares y Heterogéneas**, Universidad de Cuenca. Reúne el trabajo del equipo
en simulación de movilidad, información de ocupación del transporte urbano y
observación experimental de señales WiFi mediante ESP32.

## Trabajo del equipo

Los dos desarrollos del interciclo abordan aspectos complementarios del proyecto
**App de uso de espacio en buses**:

- **Simulación e información al pasajero — «¡Viene a full!!!»:** aplicación que
  consulta SUMO mediante TraCI, muestra buses de la Línea 3, ocupación, próximas
  llegadas y recomendaciones para quien espera en una parada.
- **Medición experimental — P5 WiFi Occupancy Lab V1:** interfaz de laboratorio
  y firmware ESP32 para estudiar la relación entre observaciones WiFi y una
  referencia de aforo manual, usando una o dos sondas en el mismo bus.

El primer componente trabaja con pasajeros y vehículos **simulados**; el segundo
registra **agregados WiFi** para su evaluación experimental. Actualmente son
aplicaciones independientes: no hay una conexión implementada que transforme
las mediciones del ESP32 en la ocupación mostrada por SUMO. Su integración y la
calibración frente al aforo real quedan como trabajo futuro.

La participación individual se conserva en el
[historial de contribuciones](https://github.com/HenBust07/RedesVehiculares/graphs/contributors).
Esta portada describe los aportes del equipo sin atribuir archivos a personas
basándose únicamente en sus nombres.

## Organización

| Ubicación | Contenido |
|---|---|
| [Interciclo/](Interciclo/) | Aplicación de buses SUMO/TraCI, demanda y mapa |
| [Interciclo/P5_WiFi_Occupancy_Lab/](Interciclo/P5_WiFi_Occupancy_Lab/) | Interfaz experimental, firmware ESP32, pruebas y documentación |
| [reto_ambulancias.py](reto_ambulancias.py) | Escenario de gestión de ambulancias en SUMO |
| [prueba_colision.py](prueba_colision.py) | Escenario de accidente entre bus y motocicleta |
| [prueba_despacho_ambulancia.py](prueba_despacho_ambulancia.py) | Despacho, atención y retorno de ambulancias |
| [tabla_hospitales.py](tabla_hospitales.py) | Cálculo de posiciones de hospitales sobre la red vial |

## Interciclo: simulación de ocupación y recomendaciones

La aplicación [ventana.py](Interciclo/ventana.py), desarrollada con Tkinter,
permite seleccionar las paradas P1, P2 y P3 y consultar información de los buses
que aún deben atenderlas. Muestra capacidad, ocupación, tiempo estimado de
llegada y recomendaciones para esperar o considerar otra alternativa.
El visor dibuja posiciones de vehículos y geometría del mapa disponible.

- [simulacion.py](Interciclo/simulacion.py): conexión TraCI, lectura de pasajeros,
  subidas y bajadas y clasificación de tiempos de movimiento, parada, semáforo
  y otras detenciones.
- [modelo.py](Interciclo/modelo.py): selección de buses por parada y reglas de
  recomendación; incluye estados de demostración identificados como tales.
- [demanda.py](Interciclo/demanda.py) y
  [demanda_pasajeros.csv](Interciclo/demanda_pasajeros.csv): lectura de demanda
  planificada y contraste con movimientos observados dentro de la simulación.
- [historial.py](Interciclo/historial.py): registro de corridas y resultados de
  SUMO en `historial_pasajeros.xlsx`, mediante openpyxl.
- [configuracion.py](Interciclo/configuracion.py): paradas, capacidad y conexión
  configurada a `127.0.0.1:3400`.
- [visor.py](Interciclo/visor.py), [exportar_mapa.py](Interciclo/exportar_mapa.py)
  y [generar_paradas_rapidas.py](Interciclo/generar_paradas_rapidas.py):
  visualización y utilidades para preparar mapa y paradas.

### Ejecución de la simulación

Se requieren Python con Tkinter, TraCI, openpyxl y un escenario SUMO preparado.
Algunas utilidades también usan sumolib. Con las dependencias disponibles y el
servidor SUMO configurado, desde la raíz del repositorio:

```powershell
Set-Location Interciclo
python ventana.py
```

La interfaz no sustituye al servidor SUMO ni prepara automáticamente el escenario.
Las redes, rutas y configuraciones completas necesarias para todas las prácticas
no están incluidas en esta versión del repositorio; deben proporcionarse y
ajustarse antes de intentar reproducirlas. Los tiempos de llegada usan una
aproximación configurada, no una predicción de tráfico validada en campo.

## P5: laboratorio WiFi con ESP32

[**README del laboratorio y pasos de reproducción**](Interciclo/P5_WiFi_Occupancy_Lab/README.md).

La aplicación usa Python, Tkinter, PySerial y Matplotlib. **SENSOR_01 y SENSOR_02
pertenecen al mismo BUS_001** y conservan resultados separados. La lectura serial
es a 115200 baudios; el firmware observa Probe Requests en canal 6 de 2,4 GHz y
produce ventanas de diez segundos.

Incluye configuración de condiciones experimentales, aforo manual con marcas
temporales, gráficas, historial y exportación CSV/PNG. Conserva observaciones en
CSV/JSONL y metadatos; detecta incidencias seriales y aborta ante pérdida de
integridad. El arranque no conecta ni inicia capturas automáticamente.

### Probar la interfaz sin hardware

Desde la raíz del repositorio, con un Python que ya tenga sus dependencias:

```powershell
Set-Location Interciclo\P5_WiFi_Occupancy_Lab
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -Diagnostico
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -Demo
```

Si es necesario, agregue `-PythonPath 'C:\ruta\python.exe'` al lanzador. Demo
usa sondas artificiales en memoria, sin puertos físicos ni radio. No instala
dependencias. El README específico explica la preparación del firmware con
ESP-IDF v5.5.6 y el procedimiento de medición real autorizada.

El estimador opcional `N = max(0, (D - B) / pd)` permanece **NO CALIBRADO**:
sus parámetros son supuestos por sonda. Las direcciones únicas no equivalen
a pasajeros y no se suman entre sondas ni ventanas.

- [Manual de utilización](Interciclo/P5_WiFi_Occupancy_Lab/captura/MANUAL_LABORATORIO.md).
- [Diagrama y descripción para el informe](Interciclo/P5_WiFi_Occupancy_Lab/docs/interfaz_laboratorio_informe.md).
- [Pruebas artificiales](Interciclo/P5_WiFi_Occupancy_Lab/tests/test_p5_lab.py).

## Prácticas de atención de emergencias

Los scripts de la raíz exploran escenarios de colisión, ubicación de hospitales
y despacho y retorno de ambulancias mediante SUMO/TraCI. Son ejercicios de
simulación, no un sistema operativo de atención de emergencias.
Referencian recursos externos como `cuenca_reto.sumocfg`, redes y rutas XML y
`hospitales.py`, ausentes en esta versión. No se presentan como ejemplos
autocontenidos ni se afirma que hayan sido ejecutados durante esta actualización.

## Evidencia, privacidad y alcance

- Separar resultados de SUMO, datos artificiales de pruebas y observaciones
  WiFi reales. Ninguno sustituye automáticamente a un aforo real de pasajeros.
- Las pruebas de software no demuestran precisión de ocupación ni rendimiento
  de radio en servicio. La calibración exige referencia experimental.
- Las mediciones WiFi requieren un entorno autorizado. El laboratorio exporta
  agregados y no almacena MAC originales, SSID ni contenido de tramas.
- El paquete P5 publicado excluye datos reales, registros privados, binarios,
  SDK y entornos instalados. No publicar mediciones sensibles por defecto.
- Mantener ambas líneas independientes hasta implementar y validar expresamente
  el intercambio de datos entre ellas.
