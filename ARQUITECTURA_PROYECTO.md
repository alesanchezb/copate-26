# Arquitectura del proyecto

## Resumen

Este proyecto simula una celda industrial de soldadura y monta un flujo completo de alertas en tiempo real. La simulacion actual ya no genera numeros aleatorios: reproduce lecturas historicas del PLC mediante tags, handshake y un adapter MQTT separado.

1. `simulator.py` levanta un PLC simulado en memoria, alimentado por datos historicos reales.
2. `plc_gateway` lee tags `NewData...`, ejecuta handshake y publica eventos normalizados por MQTT.
3. `broker` (Mosquitto) recibe esos eventos en `fabrica/linea1/soldadura`.
4. `cerebro` consume la telemetria, la normaliza por estacion, genera alertas y expone una UI propia.
5. `db` persiste estaciones, eventos de soldadura y alertas.
6. La interfaz web consulta la API del servicio `cerebro` para mostrar dashboard, historial y detalle de anomalias.

## Componentes

### 1. Simulador PLC y adapter MQTT

- Archivo: [simulator.py](/home/urias/copa_te/copate-26/simulator.py)
- Paquete: [plc_gateway](/home/urias/copa_te/copate-26/plc_gateway)
- Ejecuta fuera de Docker.
- Publica en `localhost:1883`.
- Usa como fuente primaria [WeldParameters.db](/home/urias/copa_te/copate-26/plc_reader_y_app/WeldParameters.db).
- Usa como fallback [WeldResults_10Feb_2026_24Feb_2026.csv](/home/urias/copa_te/copate-26/plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv).
- Reproduce ventanas historicas contiguas.
- Simula tags PLC y handshake:
  - `NewData{Sch}St{i}`
  - `NewData{Sch}St{i}HndShk`
  - `ForceLast`, `DistLast`, `AmpsLast`, `VoltsLast`, `WattsLast`, `ElctCtr`, `PalletId`
- Incluye estos campos operativos en MQTT:
  - `event_id`
  - `line_id`
  - `station_id`
  - `source_type`
  - `pallet_id`
  - `pallet_run_id`
  - `weld_id`
  - `timestamp`
  - `params.distancia`
  - `params.fuerza`
  - `params.ampers`
  - `params.volts`
  - `params.watts`
  - `plc.real_station`
  - `plc.schedule`
  - `plc.plc_ip`
  - `plc.electrode_count`
  - `plc.raw_id`

Contrato base:

```json
{
  "event_id": "plc-...",
  "line_id": "linea1",
  "source_type": "plc_simulator",
  "timestamp": "2026-05-12T18:30:00-07:00",
  "station_id": "station_1",
  "weld_id": 1,
  "pallet_id": "13",
  "pallet_run_id": "13-20260512T183000-0001",
  "params": {
    "distancia": 0.482,
    "fuerza": 93.0,
    "ampers": 10.62,
    "volts": 2.6,
    "watts": 7.26
  },
  "plc": {
    "real_station": "140",
    "schedule": "Sch1",
    "plc_ip": "172.16.14.1",
    "electrode_count": "652",
    "raw_id": "86539"
  }
}
```

### 2. Broker MQTT

- Servicio Docker: `broker`
- Imagen: `eclipse-mosquitto:latest`
- Configuración: [mosquitto/config/mosquitto.conf](/home/urias/copa_te/copate-26/mosquitto/config/mosquitto.conf)
- Puertos:
  - `1883` MQTT
  - `9001` reservado para WebSockets

### 3. Servicio de alertas y UI

- Servicio Docker: `cerebro`
- Código principal: [brain/main.py](/home/urias/copa_te/copate-26/brain/main.py)
- Configuración y estaciones: [brain/config.py](/home/urias/copa_te/copate-26/brain/config.py)
- Persistencia y consultas: [brain/repository.py](/home/urias/copa_te/copate-26/brain/repository.py)
- Interfaz estática:
  - [dashboard.html](/home/urias/copa_te/copate-26/brain/static/dashboard.html)
  - [history.html](/home/urias/copa_te/copate-26/brain/static/history.html)
  - [detail.html](/home/urias/copa_te/copate-26/brain/static/detail.html)
- Puerto expuesto: `8000`

Responsabilidades:

- Espera a que PostgreSQL esté disponible.
- Se conecta al broker MQTT dentro de Docker.
- Normaliza la telemetria a una estructura consistente para simulador hoy y PLC despues.
- Mapea las estaciones reales del PLC a 4 estaciones de UI:
  - `140 -> station_1` -> soldaduras 1 y 2
  - `145 -> station_2` -> soldaduras 3 y 4
  - `150 -> station_3` -> soldaduras 5 y 6
  - `155 -> station_4` -> soldaduras 7 y 8
- Calcula `weld_id` con `Sch1` como primer weld de la estacion y `Sch2` como segundo.
- Conserva `PalletId` crudo como `pallet_id`.
- Usa `pallet_run_id` para agrupar una pasada unica del pallet en detalles de alerta.
- Si el payload trae salida del modelo, la usa.
- Si no existe salida del modelo todavia, llama el hook [model.py](/home/urias/copa_te/copate-26/brain/model.py), que carga IsolationForest + scaler `joblib` desde `MODEL_DIR` (montado desde `./modelo`).
- Hoy solo `("140", "Sch1")` tiene artefactos; el resto cae al `rule_fallback` hasta que entreguen mas.
- Si el hook no devuelve inferencia, aplica `rule_fallback` temporal.
- Guarda eventos completos y crea alertas para anomalias.
- Sirve una UI operativa alineada con el material de `instrucciones/stitch`.

### 4. Base de datos

- Servicio Docker: `db`
- Imagen: `postgres:15`
- Inicialización: [db_init/init.sql](/home/urias/copa_te/copate-26/db_init/init.sql)
- Puerto expuesto: `5432`
- Persistencia:
  - volumen nombrado `postgres_data`

Tablas principales:

- `stations`
- `weld_events`
- `alerts`

`weld_events` conserva columnas legacy (`voltaje`, `corriente`, `presion`, `tiempo_ms`) para compatibilidad y agrega columnas canonicas PLC:

- `pallet_run_id`
- `distancia`
- `fuerza`
- `ampers`
- `volts`
- `watts`
- `real_station`
- `schedule`
- `plc_ip`
- `electrode_count`

## Interfaz operativa

La interfaz web reemplaza a Grafana como superficie principal del sistema y toma como referencia las vistas de `instrucciones/stitch`:

- Dashboard en tiempo real:
  - 4 estaciones en serie
  - logs recientes
  - metricas rapidas
  - alerta activa
- Historial:
  - filtros por fecha, pallet, estacion y estado
  - tabla paginada
  - resumen de resultados
- Detalle de alerta:
  - contexto del pallet
  - linea de tiempo por soldadura
  - marcadores de anomalia
  - tabla de telemetria del pallet

## Flujo de datos

```text
simulator.py
  -> SimulatedTagClient
  -> tags NewData/valores
  -> PlcMqttAdapter
  -> handshake HndShk
  -> MQTT publish a localhost:1883
  -> broker (Mosquitto)
  -> cerebro consume topic fabrica/linea1/soldadura
  -> normaliza evento
  -> genera estado / alerta
  -> INSERT en PostgreSQL
  -> UI propia consulta la API FastAPI
```

## Variables de entorno

Definidas en [.env.example](/home/urias/copa_te/copate-26/.env.example):

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `LINE_ID`
- `LINE_LABEL`
- `OPERATOR_NAME`
- `OPERATOR_LINE_LABEL`

## Comandos operativos

Levantar infraestructura:

```bash
docker compose up --build -d
```

Ver logs:

```bash
docker compose logs -f broker cerebro db
```

Abrir interfaz:

```text
http://localhost:8000
```

Ejecutar simulador local:

```bash
python3 simulator.py
```

Opciones utiles:

```bash
python3 simulator.py --limit 100
python3 simulator.py --timestamp-mode historical
python3 simulator.py --speed 8
```

## Observaciones importantes

- El sistema ya no depende de Grafana para la operacion principal.
- La UI corre dentro del mismo servicio que procesa alertas.
- El fallback por reglas es solo una compatibilidad temporal mientras se integra el equipo de ML.
- El contrato de entrada ya esta alineado a un adaptador PLC real.
- El puerto `1883` expuesto por Docker permite que el simulador corra desde el host y publique al broker del contenedor.
- `PalletId` fisico se reutiliza; no debe usarse como identificador unico de pasada.
- `pallet_run_id` cierra una pasada al completar los 8 slots estacion/schedule o por timeout de 5 minutos.

## Decisiones de rendimiento y robustez (revision 2026-05-12)

- `brain/repository.py` usa un `ThreadedConnectionPool` global (1..10) en lugar de abrir una conexion psycopg2 por request. Sin pool, los polls cada 2.5 s del dashboard y los `JOIN` por estacion mataban el tiempo de respuesta de `/api/dashboard` y `/api/history`.
- `fetch_history_data` envuelve el COUNT en un subquery con `LIMIT 5001` y expone `count_capped`. Con `weld_events` creciendo via simulador (la fuente historica tiene ~1.3 M filas), un COUNT global tomaba segundos y bloqueaba el historial.
- El simulador PLC (`plc_gateway/simulation.py`) espera el ciclo completo del handshake (1 -> 0) antes de bajar `NewData`. Esto reproduce el comportamiento PLC real y evita la perdida de muestras consecutivas en el mismo `(station, schedule)` cuando el productor adelantaba el ciclo al adapter.
- `evaluate_rule_fallback` en la rama PLC (`ampers`/`volts`) usa umbrales fuera de banda (`ampers > 13.5`, `volts < 1.8`) con threshold de severidad `>= 0.5`. Antes marcaba como `MALO` cualquier amperaje `> 12.5`, lo que inundaba `alerts` con datos reales que normalmente pasan de 12.5.
- `dashboard.js` aplica un guard `inflight` para evitar que requests se apilen cuando la API tarda, y polling pasa de 2.5 s a 5 s.
- Tailwind se sigue cargando via CDN (`cdn.tailwindcss.com`). Compila estilos en cliente y es la causa principal del primer pintado tardio; queda pendiente reemplazar por CSS pre-compilado.

## Estado actual del conocimiento

Este archivo resume la arquitectura refactorizada observada en el codigo al 2026-05-12 y sirve como contexto persistente para futuras sesiones.
