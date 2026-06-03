# Arquitectura del proyecto

## Resumen ejecutivo

El sistema monitorea soldadura de busbars en una celda industrial. Cada pallet fisico contiene 8 busbars y pasa por 4 estaciones. Cada estacion genera dos lecturas por pallet: `Sch1` y `Sch2`.

La arquitectura queda dividida por fronteras claras:

1. `plc_gateway` sabe leer tags tipo PLC y convertirlos a eventos MQTT normalizados.
2. `simulator.py` usa `plc_gateway` con un cliente de tags en memoria para pruebas locales.
3. `plc_adapter.py` usa `plc_gateway` con `pylogix` para PLC real.
4. Mosquitto recibe eventos en `fabrica/linea1/soldadura`.
5. `brain` consume MQTT, normaliza, evalua modelo/reglas, persiste y sirve la UI.

`brain` no depende del PLC ni de `pylogix`. Esto permite desarrollar con simulador y despues instalar el adapter real sin reescribir la aplicacion.

## Veredicto de implementabilidad PLC

El proyecto es implementable en planta si se respeta esta frontera:

- El equipo de planta ejecuta `plc_adapter.py` en una maquina con red hacia los PLC.
- Ese adapter publica al broker MQTT el mismo contrato que usa el simulador.
- `brain` sigue dentro de Docker consumiendo `fabrica/linea1/soldadura`.
- Las IPs, tags `NewData...`, tags de valores y handshake coinciden con la referencia real ubicada en `references/planta/plc_reader_y_app/`.

La revision contra el codigo real de planta confirma que se conservaron los puntos importantes:

- Lectura por `NewData{Sch}St{i}`.
- Valores `ForceLast`, `DistLast`, `AmpsLast`, `VoltsLast`, `WattsLast`, `ElctCtr`, `PalletId`.
- Handshake `NewData{Sch}St{i}HndShk` con pulso `1 -> 0`.
- Dos PLCs para las cuatro estaciones de soldadura.
- `PalletId` conservado aun si es `0` o negativo.

## Mapeo PLC

| PLC | Slot local | Estacion real | UI | Welds |
| --- | --- | --- | --- | --- |
| `172.16.14.1` | `St1` | `140` | `station_1` | `1`, `2` |
| `172.16.14.1` | `St2` | `145` | `station_2` | `3`, `4` |
| `172.16.15.1` | `St1` | `150` | `station_3` | `5`, `6` |
| `172.16.15.1` | `St2` | `155` | `station_4` | `7`, `8` |

`Sch1` es el primer weld de la estacion y `Sch2` el segundo.

## Contrato MQTT

Topic:

```text
fabrica/linea1/soldadura
```

Ejemplo:

```json
{
  "event_id": "plc-...",
  "line_id": "linea1",
  "source_type": "plc_real",
  "timestamp": "2026-05-29T14:30:00-07:00",
  "station_id": "station_1",
  "weld_id": 1,
  "pallet_id": "13",
  "pallet_run_id": "13-20260529T143000-0001",
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
    "raw_id": null,
    "raw_timestamp": null
  }
}
```

`pallet_id` es el `PalletId` crudo del PLC. `pallet_run_id` es la pasada operativa unica que usa la UI para detalle y linea de tiempo.

## Componentes

### `plc_gateway/`

Contiene la frontera industrial:

- `mapping.py`: IPs, estaciones, schedules, nombres de tags y weld IDs.
- `clients.py`: `SimulatedTagClient` y `PylogixTagClient`.
- `adapter.py`: barrido de flags, lectura de tags, handshake y publicacion MQTT.
- `simulation.py`: productor historico que alimenta el PLC simulado.
- `sources.py`: carga ventanas historicas desde SQLite o CSV.
- `run_tracker.py`: construye `pallet_run_id` por pasada.

### `simulator.py`

Entrada local para pruebas. Usa `SimulatedTagClient`, reproduce ventanas historicas contiguas y emite eventos MQTT.

Fuentes:

1. `data/WeldParameters.db`
2. `references/planta/plc_reader_y_app/WeldParameters.db`
3. `references/planta/plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv`

### `plc_adapter.py`

Entrada de planta. Usa `PylogixTagClient` para leer los PLC reales y publicar el mismo contrato MQTT. No guarda en base de datos local y no sirve UI; solo traduce PLC a MQTT.

### `brain/`

Servicio FastAPI que:

- espera PostgreSQL;
- siembra estaciones;
- consume MQTT;
- normaliza payloads;
- llama `brain/model.py`;
- aplica fallback conservador si no hay modelo;
- persiste `weld_events` y `alerts`;
- expone dashboard, historial, analitica y detalle.

### `onnx_models/`

Directorio montado read-only como `/app/onnx_models` dentro de `cerebro`.

Modelos exactos actuales:

- `150_Sch1`
- `155_Sch2`

No se interpolan modelos entre estaciones porque las distribuciones no son intercambiables.

### `references/`

Material que explica o respalda el proyecto, pero no se ejecuta como parte del sistema:

- `references/planta/plc_reader_y_app/`: codigo real de planta usado como referencia.
- `references/diseno/instrucciones/`: material visual y guias de interfaz.
- `references/modelos_legacy/modelo/`: scripts y artefactos ML anteriores.

## Modelo y reglas

`brain/model.py` recibe:

- `distancia`
- `watts`
- `distancia_delta`
- `fuerza_delta`
- `watts_delta`

Los deltas se calculan en tiempo real por `(real_station, schedule)` y se clampean con `onnx_models/clamps.json`.

Mapeo operativo:

- `BUENA` y `POSIBLE_BUENA` se guardan como `BUENO`.
- `POSIBLE_MALA` y `MALA` se guardan como `MALO` y crean alerta.
- Si `onnxruntime` no esta disponible, falta modelo o no existe la combinacion exacta, el hook regresa `None`.
- `rule_fallback` solo marca `MALO` cuando `ampers > 13.5` o `volts < 1.8` con score `>= 0.5`.

## Persistencia

`brain/repository.py` usa un `ThreadedConnectionPool` global. Las escrituras usan `with get_connection() as conn:` y hacen `conn.commit()` explicito.

Tablas principales:

- `stations`
- `weld_events`
- `alerts`

`fetch_history_data` mantiene un cap de conteo con `LIMIT 5001` y expone `count_capped` para evitar consultas costosas sobre historicos grandes.

## Verificacion esperada

Unit tests:

```bash
python3 -m unittest
```

Smoke local:

```bash
docker compose up --build -d
python3 simulator.py --limit 100
curl http://localhost:8000/api/dashboard
```

Smoke PLC real:

```bash
python3 plc_adapter.py --broker <IP_BROKER> --topic fabrica/linea1/soldadura
```

Validar en logs de `cerebro` que lleguen eventos con `source_type=plc_real` y que la UI muestre telemetria activa.
