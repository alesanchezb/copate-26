# Arquitectura del proyecto

## Resumen

Este proyecto simula una celda industrial de soldadura y monta un flujo completo de observabilidad y persistencia:

1. `simulator.py` genera eventos de soldadura y los publica por MQTT.
2. `broker` (Eclipse Mosquitto) recibe esos eventos en `fabrica/linea1/soldadura`.
3. `cerebro` consume los mensajes, clasifica cada soldadura como `BUENO` o `MALO` y la guarda en PostgreSQL.
4. `db` almacena el histórico en la tabla `registros_soldadura`.
5. `grafana` se provisiona con PostgreSQL como fuente de datos para consultar y visualizar registros.

## Componentes

### 1. Simulador

- Archivo: [simulator.py](/home/urias/copa_te/copate-26/simulator.py)
- Ejecuta fuera de Docker.
- Publica en `localhost:1883`.
- Emite 8 soldaduras por pallet con parámetros sintéticos:
  - `voltaje`
  - `corriente`
  - `presion`
  - `tiempo_ms`

Ejemplo lógico del payload:

```json
{
  "pallet_id": "PALLET_1000",
  "weld_id": 1,
  "timestamp": 1710000000.0,
  "params": {
    "voltaje": 12.1,
    "corriente": 449.8,
    "presion": 3.02,
    "tiempo_ms": 801
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
- Modo actual:
  - `allow_anonymous true`

### 3. Cerebro de análisis

- Servicio Docker: `cerebro`
- Código: [brain/main.py](/home/urias/copa_te/copate-26/brain/main.py)
- Imagen construida desde: [brain/Dockerfile](/home/urias/copa_te/copate-26/brain/Dockerfile)
- Dependencias embebidas en la imagen:
  - `paho-mqtt`
  - `psycopg2-binary`
  - Python 3.10 slim

Responsabilidades:

- Espera 10 segundos al arranque para dar tiempo a `broker` y `db`.
- Se conecta al broker MQTT dentro de la red Docker usando el host `broker`.
- Se suscribe al topic `fabrica/linea1/soldadura`.
- Determina el estado de calidad:
  - `MALO` si `voltaje > 12.5` o `presion < 2.8`
  - `BUENO` en cualquier otro caso
- Inserta en PostgreSQL:
  - `pallet_id`
  - `weld_id`
  - `voltaje`
  - `presion`
  - `estado`

Nota:

- `corriente` y `tiempo_ms` se generan en el simulador, pero hoy no se persisten en la base de datos.

### 4. Base de datos

- Servicio Docker: `db`
- Imagen: `postgres:15`
- Inicialización: [db_init/init.sql](/home/urias/copa_te/copate-26/db_init/init.sql)
- Puerto expuesto: `5432`
- Persistencia:
  - volumen nombrado `postgres_data`

Esquema actual:

- Tabla `registros_soldadura`
  - `id`
  - `pallet_id`
  - `weld_id`
  - `voltaje`
  - `presion`
  - `estado`
  - `timestamp`

### 5. Grafana

- Servicio Docker: `grafana`
- Imagen: `grafana/grafana-oss:latest`
- Puerto expuesto: `3000`
- Persistencia:
  - volumen nombrado `grafana_data`
- Provisioning datasource:
  - [grafana_provisioning/datasources/postgres.yml](/home/urias/copa_te/copate-26/grafana_provisioning/datasources/postgres.yml)

Comportamiento:

- Usa PostgreSQL del servicio `db` como datasource por defecto.
- Toma credenciales desde variables de entorno.

## Red y flujo de datos

Todos los contenedores usan la red bridge `red_industrial`.

Flujo end-to-end:

```text
simulator.py
  -> MQTT publish a localhost:1883
  -> broker (Mosquitto)
  -> cerebro consume topic fabrica/linea1/soldadura
  -> clasifica BUENO/MALO
  -> INSERT en PostgreSQL
  -> Grafana consulta PostgreSQL
```

## Variables de entorno

Definidas en [.env.example](/home/urias/copa_te/copate-26/.env.example):

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `GRAFANA_ADMIN_PASSWORD`

`docker-compose.yml` depende de esas variables para `db`, `cerebro` y `grafana`.

## Comandos operativos

Levantar infraestructura:

```bash
docker compose up --build -d
```

Ver logs:

```bash
docker compose logs -f broker cerebro db grafana
```

Ejecutar simulador local:

```bash
python3 simulator.py
```

Detener servicios:

```bash
docker compose down
```

## Observaciones importantes

- No existe un backend HTTP expuesto; el corazón del sistema es mensajería MQTT + procesamiento + persistencia.
- `cerebro` importa `fastapi` y `uvicorn` en su imagen, pero el código actual no los usa.
- `depends_on` asegura orden de arranque, pero no healthchecks reales.
- El `sleep(10)` en `brain/main.py` compensa parcialmente la falta de healthchecks.
- Para que Grafana vea datos, además de levantar Docker hace falta ejecutar `simulator.py`.
- El puerto `1883` expuesto por Docker permite que el simulador corra desde el host y publique al broker del contenedor.
- Los datos persistentes de PostgreSQL y Grafana usan volúmenes nombrados de Docker para evitar problemas de permisos del host y mejorar la portabilidad del proyecto entre máquinas.

## Estado actual del conocimiento

Este archivo resume la arquitectura real observada en el código al 2026-04-11 y sirve como contexto persistente para futuras sesiones.
