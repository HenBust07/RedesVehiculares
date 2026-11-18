# Requisitos P5 proporcionados por el usuario

Fuente: texto entregado por el usuario durante la fase de organización y validación. Se conserva su contenido, organizado para lectura. No se proporcionaron puntuaciones o ponderaciones.

## App de uso de espacio en buses

Aplicación que estima y muestra el nivel de ocupación de los buses urbanos a partir de señales WiFi de los dispositivos a bordo, para informar al usuario antes de abordar y a la operadora para ajustar la oferta.

| Dato | Modelo | Acción | Medida |
|---|---|---|---|
| Dispositivos WiFi detectados a bordo del bus | Estimador de nivel de ocupación: bajo, medio, alto | Aplicación que informa la ocupación al usuario y a la operadora | Precisión del estimador frente al aforo real |
| Datos sintéticos justificados: dispositivos simulados por ocupación, para desarrollar; conteo de puerta o aforo real para calibrar | Modelo calibrado con filtrado de dispositivos fijos | Recomendación de bus alternativo | Prueba de campo en una línea urbana |

El texto distingue componentes básicos y componentes esperados. Esta tabla conserva las dos filas del contenido recibido; no asigna puntuaciones.

## Novedades de la sesión

- Estimar el nivel de ocupación mediante WiFi: conteo de dispositivos.
- Revisar la literatura y traer el resultado a la siguiente revisión.

## Entregables

- **Presentación:** método de estimación, prueba de campo o simulada y la aplicación mostrando la ocupación por bus.
- **Informe:** revisión de literatura sobre estimación de ocupación mediante WiFi, Bluetooth y visión; calibración del conteo frente a la ocupación real, precisión obtenida y consideraciones de privacidad.
- **Prototipo:** sonda de captura WiFi, ESP32 o portátil, con su firmware o script; servicio que convierte dispositivos detectados en nivel de ocupación; aplicación móvil o web para el usuario; conjunto de datos de calibración.

## Alcance actual

En esta fase únicamente se organiza el proyecto y se valida Hello World. Se documentan los demás requisitos para el desarrollo incremental posterior. No se implementa el sniffer, no se capturan señales inalámbricas, no se realiza aún la revisión bibliográfica ni se redacta el informe académico definitivo. Una prueba simulada debe identificarse como simulada y no sustituye evidencia real de calibración o campo cuando se declare haberla realizado.
