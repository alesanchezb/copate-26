# Arquitectura del proyecto

## Resumen

Este proyecto simula una celda industrial de soldadura y monta un flujo completo de alertas en tiempo real:

1. `simulator.py` genera eventos de soldadura y los publica por MQTT.
2. `broker` (Mosquitto) recibe esos eventos en `fabrica/linea1/soldadura`.
3. `cerebro` consume la telemetria, la normaliza por estacion, genera alertas y expone una UI propia.
4. `db` persiste estaciones, eventos de soldadura y alertas.
5. La interfaz web consulta la API del servicio `cerebro` para mostrar dashboard, historial y detalle de anomalias.

## Componentes

### 1. Simulador

- Archivo: [simulator.py](/home/urias/copa_te/copate-26/simulator.py)
- Ejecuta fuera de Docker.
- Publica en `localhost:1883`.
- Emite 8 soldaduras por pallet.
- Incluye estos campos operativos:
  - `event_id`
  - `line_id`
  - `station_id`
  - `source_type`
  - `pallet_id`
  - `weld_id`
  - `timestamp`
  - `params.voltaje`
  - `params.corriente`
  - `params.presion`
  - `params.tiempo_ms`

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
- Mapea las 8 soldaduras del pallet a 4 estaciones:
  - `station_1` -> soldaduras 1 y 2
  - `station_2` -> soldaduras 3 y 4
  - `station_3` -> soldaduras 5 y 6
  - `station_4` -> soldaduras 7 y 8
- Si el payload trae salida del modelo, la usa.
- Si no existe salida del modelo todavia, aplica un fallback temporal por reglas:
  - `MALO` si `voltaje > 12.5`
  - `MALO` si `presion < 2.8`
  - `BUENO` en otro caso
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

## Observaciones importantes

- El sistema ya no depende de Grafana para la operacion principal.
- La UI corre dentro del mismo servicio que procesa alertas.
- El fallback por reglas es solo una compatibilidad temporal mientras se integra el equipo de ML.
- El contrato de entrada ya esta mas cerca de un futuro adaptador hacia PLC.
- El puerto `1883` expuesto por Docker permite que el simulador corra desde el host y publique al broker del contenedor.

## Estado actual del conocimiento

Este archivo resume la arquitectura refactorizada observada en el codigo al 2026-04-12 y sirve como contexto persistente para futuras sesiones.
