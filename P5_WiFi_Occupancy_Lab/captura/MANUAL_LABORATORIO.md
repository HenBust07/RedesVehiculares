# P5 WiFi Occupancy Lab V1 — manual breve

Aplicacion local de laboratorio, sin backend ni aplicacion de pasajeros.
El modelo permanece **NO CALIBRADO**. Una direccion WiFi no equivale a una persona.

## Iniciar sin instalar dependencias

Desde `D:\RVH\P5_OCUPACION_BUSES`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1
```

Se reutiliza Python 3.14.3 existente con Tkinter 8.6, PySerial 3.5 y Matplotlib
3.10.8. El Python de ESP-IDF 3.11.7 carece de Tkinter/Matplotlib y no se modifica.
No hace falta activar ESP-IDF ni instalar otro framework o entorno virtual.
La politica de ejecucion y las variables son del proceso; no cambia PATH global.

```powershell
# Comprobar dependencias, sin ventana ni apertura de puertos:
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -Diagnostico
# Practicar exclusivamente con sondas artificiales, sin radio:
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -Demo
# Otro interprete YA instalado que tenga todas las dependencias:
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -PythonPath 'C:\ruta\python.exe'
```

Demo muestra **SINTETICO**, usa `SIM_BUS_001/002` en memoria y tiempos acelerados
(por defecto 10 s del ESP simulado por 1 s PC). No es evidencia de radio real.
La aplicacion enumera puertos, pero nunca conecta ni envia START al abrirse.

Ambas sondas pertenecen al mismo **BUS_001**: SENSOR_01 y SENSOR_02 se muestran
por separado, sin fusionar sus detecciones. Los nuevos CSV/JSONL incluyen
`bus_id=BUS_001` y `probe_id=SENSOR_01` o `SENSOR_02`. El campo `sensor_id`
conserva el identificador serial heredado del firmware (BUS_001/BUS_002) para
verificar cada placa; ese campo no representa dos buses. Los metadatos guardan
la correspondencia. Los experimentos previos se conservan sin reescribir ni
asignarles retroactivamente un bus que no habian registrado.
La ventana inicial se ajusta al espacio disponible de la pantalla. Las tarjetas
laterales y las cuatro pestañas tienen barras de desplazamiento vertical y
horizontal: permiten llegar a los controles y gráficas completos en ventanas
pequeñas. Use la rueda para bajar/subir y Mayús + rueda para desplazarse
horizontalmente. Arrastre el separador central para ajustar el ancho lateral.
Ctrl + Tab cambia de pestaña. El registro de incidencias tiene además su propia
barra vertical. «Desc. C/T/B» indica descartes de cola, tabla y borde.
Después de actualizar el código, cierre y vuelva a abrir la aplicación para
aplicar los cambios; una ventana ya abierta conserva la versión anterior.

## Primer experimento con una o ambas sondas

1. Cierre otros monitores seriales. Actualice puertos y seleccione la placa de
   cada tarjeta. Historicamente SENSOR_01/CH340 estaba en COM9 y SENSOR_02/CP210x en
   COM11; Windows puede cambiar estos numeros. No seleccione por orden numerico.
2. Pulse **Conectar / verificar** individualmente. Reinicia solo esa sonda y
   verifica las 19 autopruebas con radio apagada. Espere «Lista, radio OFF».
   El puente USB debe coincidir con la placa esperada; un COM no es una identidad.
3. Marque «Incluir en el experimento» para una o las dos sondas. No es necesario
   que haya dos telefonos: la cantidad es configurable o puede declararse desconocida.
4. En **Experimento / parametros**, elija modalidad y P0–P9; documente duracion,
   cantidad de telefonos, ubicacion, distancia/geometria, WiFi, pantalla,
   actividad y observaciones. Aforo inicial vacio significa no observado, nunca cero.
5. Si desea estimaciones, habilitelas por sonda e introduzca B y pd explicitamente.
   Sin parametros validos no se habilita el inicio con ese modelo. Si no solicita
   estimacion, se adquieren los agregados y se guardan estimaciones null.
6. Confirme un entorno autorizado y la correspondencia fisica de las placas.
   Pulse **Iniciar manualmente**. La confirmacion no se reutiliza en otro experimento.
7. Observe graficas, estado, canal efectivo, probes, unicos, RSSI, heap, descartes,
   estimacion, aforo y error. Selector Ambas/SENSOR_01/SENSOR_02 para vista comparativa
   o individual. El canal 6 solo se marca efectivo al confirmarlo el firmware.
8. En **Aforo / incidencias**, registre cada cambio de aforo y notas del operador.
   Se guardan sus instantes monotónicos PC. No escriba MAC, SSID o datos personales.
9. **Pausar** envia STOP a ambas participantes y espera confirmacion. La ventana
   parcial se descarta y se registra; no se rellena con cero. **Reanudar** requiere
   accion manual y abre nuevos segmentos, distinguiendo la pausa de una perdida.
10. **Detener y cerrar**, alcanzar duracion o cerrar la aplicacion detiene las
    sondas y cierra los puertos. Para otro experimento, vuelva a conectar/verificar.

### Limite de identidad del firmware actual

El firmware no tiene comando INFO que informe BUS_001/BUS_002 con radio apagada.
Antes de START se muestra identidad **esperada**, basada en seleccion/puente USB
y autopruebas. La identidad se verifica al primer JSON de una captura iniciada
manualmente; una discrepancia aborta ambas sondas sin guardar ese registro.
Esto no es autenticacion criptografica. No se envia START para descubrir puertos.

### Duracion, bloques y pausas

Cada firmware produce ventanas completas de 10 s y termina tras doce ventanas
(120 s nominales). Duraciones menores de una ventana pueden no producir datos;
un archivo sin ventanas no representa cero personas. Se recomienda comenzar con
120 s. El cronometro cuenta tiempo PC activo, excluyendo pausas confirmadas;
puede diferir del tiempo de observacion sumado de ventanas y del arranque WiFi.

Para duraciones mayores de 120 s debe marcar explicitamente la autorizacion
de bloques sucesivos dentro de ESE experimento. El coordinador solicita un
nuevo START al terminar un bloque mientras no se haya agotado la duracion.
Cada limite queda registrado como segmento intencional, sin prometer cobertura
continua durante el reinicio del receptor. Nunca renueva tras error, pausa,
detencion, desconexion o fuera del experimento iniciado manualmente.

## Plantillas propuestas P0–P9

No habia definiciones P0–P9 en la rubrica. Son propuestas editables de V1,
no protocolos aprobados ni resultados supuestos; condiciones reales deben anotarse.

| Plantilla | Objetivo propuesto |
|---|---|
| P0 | Fondo, sin telefonos de prueba; equipos externos pueden seguir presentes |
| P1 | WiFi encendido, pantalla activa y reposo |
| P2 | Pantalla apagada, comparacion con P1 |
| P3 | Actividad WiFi definida por operador |
| P4 | Distancia, manteniendo otras condiciones documentadas |
| P5 | Cantidad variable de telefonos, no limitada a dos |
| P6 | WiFi apagado en telefonos de prueba como control negativo |
| P7 | Entradas/salidas y cambios de aforo manual |
| P8 | Ubicacion/geometria |
| P9 | Escenario real autorizado con referencia manual |

## Estimador preliminar independiente

`captura/p5_lab/model.py`: `N = max(0, (D - B) / pd)`.
D es unicos de UNA sonda en UNA ventana; B es fondo asumido y pd una probabilidad
asumida. Exige B finito >= 0 y 0 < pd <= 1, con resultado finito para el rango
de la tabla. Campos B/pd empiezan vacios y el modelo deshabilitado.
No existen valores calibrados por defecto ni se estima una cifra conjunta.

Los parametros se congelan al iniciar, se guardan en metadatos y cada fila.
El resultado es continuo, no se redondea para aparentar exactitud. Aforo ausente
produce error absoluto null, no cero. Error absoluto usa el ultimo aforo manual
observado al recibir la ventana en PC, sin afirmar alineacion con los diez
segundos medidos por el ESP. No es una precision validada frente a aforo real.

## Integridad y tiempo

- Un lector por sonda, coordinador de persistencia separado y Tk en el hilo principal.
- UTF-8 estricto en registros, conjunto exacto de campos, claves duplicadas/NaN/Inf
  rechazados, tipos/rangos/RSSI/conservacion de cola y secuencia verificados.
- Reinicio, ID incorrecto, duplicado, ventana faltante, silencio >15 s durante
  captura, desconexion o cola de eventos desbordada abortan la medicion completa.
- El preambulo ROM anterior a las autopruebas puede contener ruido de arranque;
  se registra solo su longitud, nunca sus bytes. Despues de comenzar pruebas o
  adquirir, una corrupcion no se ignora ni se reconstruye como JSON valido.
- Se solicita STOP a participantes, se cierran puertos y se preserva el prefijo
  valido. Si no hay confirmacion serial se solicita reset al arranque con radio
  apagada y se indica que la parada no fue confirmada; el reset electrico no se
  da por demostrado. El firmware conserva su limite de bloque de 120 s.
- Cada fila guarda `window_start_ms` del ESP, `host_monotonic_ns` y UTC de
  recepcion de la aplicacion. Las graficas usan tiempo PC relativo comun;
  incluyen pausas en el eje horizontal y separan segmentos, sin interpolar huecos.
  No se infiere sincronizacion exacta ni una hora comun de los relojes ESP.
- Las graficas en vivo muestran las ultimas 720 ventanas por sonda; los archivos
  y estadisticas conservan todas las ventanas validas. No se suman unicos.

## Archivos e historial

Reales: `data/raw/p5_lab/<experimento>/` (excluidos de Git).
Artificiales: `data/synthetic/p5_lab/<experimento>/` (origen SINTETICO declarado).
Se crean nombres unicos, sin sobrescribir ensayos anteriores.

- `metadata.json`: condiciones, parametros, origen, puertos, reloj, estado y cierre.
- `observations.jsonl`: fuente autoritativa, solo ventanas agregadas validas.
- `observations.csv`: las mismas ventanas con UTF-8 BOM para Windows.
- `manual_counts.csv`: cambios de aforo e instantes PC, sin inventar referencias.
- `events.jsonl`: inicios, segmentos, pausas, detenciones e incidencias estructuradas.
- `summary.json`: estadisticas por sonda; no fusion ni suma de unicos.

Se guardan y vacian buffers por ventana. Ante cierre inesperado del proceso,
metadatos pueden quedar `in_progress`: revisar incidencias. Historial conserva
solo el prefijo valido si encuentra archivo truncado/corrupto, e informa la
limitacion. Nunca rellena datos ausentes ni reemplaza null por cero.

En **Historial / comparacion**, cargue metadata.json de hasta cuatro experimentos
o el ultimo terminado. Las filas indican experimento, origen y condicion.
Seleccione una y abra **Ficha / estadisticas** para condiciones, B/pd y todas
las medias/desviaciones. Puede exportar sus ventanas a CSV y el comparativo a
PNG con nombres nuevos. Por defecto no se compara real con sintetico; una opcion
permite visualizarlos manteniendo estadisticas/origen separados.

La desviacion es muestral (n-1); con n < 2 se muestra ausente. RSSI omite null.
Porcentaje sin detecciones significa ventanas con cero Probe Requests entre
ventanas validas recibidas, NO ausencia de personas. Experimentos distintos se
comparan por tiempo relativo de cada uno, no por un reloj ESP compartido.
Los historicos nuevos usan instantes manuales originales para graficar aforo.
La linea escalonada mantiene como referencia el ultimo aforo observado hasta
la siguiente actualizacion o ultima ventana: no crea observaciones manuales
adicionales ni completa ventanas de captura ausentes.

## Validacion reproducible sin radio

```powershell
& 'C:\Users\luism\AppData\Local\Python\pythoncore-3.14-64\python.exe' -B -X utf8 tests/run_p5_lab.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_laboratorio.ps1 -PruebaInterfaz
```

La suite utiliza transportes artificiales con hilos independientes y corrupcion,
saltos, duplicados, reinicios/desconexiones y fallos de disco inyectados. Los
fixtures estan separados en `data/synthetic/p5_lab_tests/`; los resultados y
PNG sinteticos en `results/lab_v1/`. No prueba el estado actual de USB ni el
comportamiento simultaneo de las placas fisicas. La primera prueba real de la
GUI queda para un entorno autorizado confirmado por el operador.

AP privado, cambio dinamico de canal, backend y aplicacion de pasajeros estan
fuera de esta version. No se modifica ni se flashea firmware desde la GUI.
No hay instalacion automatica. Inicio de medicion requiere margen preventivo
de 1,5 GB en C: y D:, manteniendo al menos 1 GB operativo.

Referencias oficiales del mecanismo de interfaz:
[Tkinter y sus hilos](https://docs.python.org/3.14/library/tkinter.html),
[integracion Tk/Matplotlib](https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_tk_sgskip.html)
y [API PySerial](https://pyserial.readthedocs.io/en/latest/pyserial_api.html).
