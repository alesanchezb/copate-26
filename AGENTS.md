# Estandares del proyecto

## Contexto operativo

- El sistema monitorea soldadura de busbars en una celda industrial.
- Cada pallet fisico contiene 8 busbars y pasa por 4 estaciones.
- Cada estacion tiene 2 schedules: `Sch1` y `Sch2`.
- El valor crudo `PalletId` del PLC identifica un pallet fisico reutilizable, no una pasada unica.
- Para UI, detalle e inferencia se usa `pallet_run_id` como identificador de una pasada operativa.

## Frontera PLC

- `references/planta/plc_reader_y_app/` es referencia real de planta, no dependencia directa de produccion del proyecto.
- La frontera de integracion es un adapter MQTT separado que publica en `fabrica/linea1/soldadura`.
- `brain` no debe leer tags PLC directamente; solo consume eventos MQTT normalizados.
- El simulador debe usar tags y handshake tipo PLC:
  - bandera: `NewData{Sch}St{i}`
  - ack: `NewData{Sch}St{i}HndShk`
  - valores: `ForceLast`, `DistLast`, `AmpsLast`, `VoltsLast`, `WattsLast`, `ElctCtr`, `PalletId`

## Mapeo de estaciones

- `140 -> station_1`, `weld_id 1/2`
- `145 -> station_2`, `weld_id 3/4`
- `150 -> station_3`, `weld_id 5/6`
- `155 -> station_4`, `weld_id 7/8`
- `Sch1` es el primer weld de la estacion y `Sch2` el segundo.
- Los tags `St1/St2` son locales a cada PLC:
  - `172.16.14.1`: real `140 -> St1`, real `145 -> St2`
  - `172.16.15.1`: real `150 -> St1`, real `155 -> St2`

## Datos historicos

- Fuente primaria local del simulador: `data/WeldParameters.db`.
- Fallback compatible: `references/planta/plc_reader_y_app/WeldParameters.db`.
- Fallback portable final: `references/planta/plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv`.
- El simulador reproduce ventanas historicas contiguas para conservar ritmo e intercalado real.
- `PalletId` 0 o negativo se conserva como dato normal; no se filtra.

## Modelo ML

- El hook de integracion vive en `brain/model.py` y carga CleaNet ONNX desde `ONNX_MODEL_DIR` (default `/app/onnx_models`, montado read-only desde `./onnx_models`).
- Registro por `{real_station}_{schedule}`. Hoy existen `150_Sch1` y `155_Sch2`; el resto queda sin inferencia de modelo porque sus distribuciones no son intercambiables.
- CleaNet recibe `distancia`, `watts`, `distancia_delta`, `fuerza_delta`, `watts_delta`; los deltas se calculan en tiempo real por `(real_station, schedule)` y se clampean con `clamps.json`.
- `BUENA` y `POSIBLE_BUENA` se guardan como `BUENO`; `POSIBLE_MALA` y `MALA` se guardan como `MALO` y crean alerta.
- Si `onnxruntime` no esta disponible, no hay modelo cargable o la combinacion no tiene modelo exacto, el hook regresa `None` y se usa `rule_fallback`. No abortar el servicio.
- El `rule_fallback` PLC marca `MALO` solo cuando `ampers > 13.5` o `volts < 1.8` con score `>= 0.5`. Mantenerlo conservador para no inundar `alerts` con telemetria que el modelo final descartaria.
- No mezclar reglas temporales con el contrato del modelo final.

## Persistencia y consultas

- `brain/repository.py` mantiene un `ThreadedConnectionPool` global. Las nuevas funciones deben usar `with get_connection() as conn:` y siempre llamar `conn.commit()` explicito cuando escriben (el context manager solo hace rollback en `finally`).
- `fetch_history_data` cuenta con `LIMIT 5001` y expone `count_capped`. No quitar el cap sin un esquema de conteo aproximado o particionado por fecha.

## Handshake del simulador

- `HistoricalPlcProducer.emit_sample` espera handshake `1 -> 0` antes de bajar `NewData`. Esto evita carreras con el adapter. Cambios al ciclo deben pasar `tests/test_plc_gateway.py::test_simulated_handshake_publishes_once_and_clears_flag`.

## Verificacion esperada

- Unit tests: `python3 -m unittest`.
- Smoke local:
  - `docker compose up --build -d`
  - `python3 simulator.py`
  - revisar `http://localhost:8000`, `/api/dashboard` y detalle de alertas.
