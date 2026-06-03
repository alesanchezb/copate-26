# Estructura del proyecto

## Regla principal

La raiz del repositorio debe contener solo lo que se ejecuta, configura o verifica. Todo lo que sea referencia historica, diseno o codigo antiguo vive en `references/`.

## Carpetas operativas

| Ruta | Uso |
| --- | --- |
| `brain/` | Servicio principal: FastAPI, consumidor MQTT, UI, modelo y repositorio PostgreSQL. |
| `plc_gateway/` | Logica comun para leer tags PLC/simulados y publicar MQTT. |
| `db_init/` | SQL inicial para PostgreSQL. |
| `mosquitto/` | Configuracion del broker MQTT. |
| `onnx_models/` | Modelos CleaNet usados por `brain/model.py`. |
| `data/` | Fuente historica local primaria para el simulador. |
| `tests/` | Pruebas unitarias. |

## Archivos operativos en raiz

| Archivo | Uso |
| --- | --- |
| `docker-compose.yml` | Levanta broker, PostgreSQL y `cerebro`. |
| `.env.example` | Plantilla de variables locales. |
| `simulator.py` | Ejecucion local con PLC simulado. |
| `plc_adapter.py` | Ejecucion en planta con PLC real. |
| `README.md` | Guia rapida de arranque. |
| `ARQUITECTURA_PROYECTO.md` | Contrato tecnico del sistema. |
| `requirements.txt` | Dependencias Python minimas para scripts locales. |
| `pyproject.toml` | Metadata del proyecto Python. |

## Carpeta `references/`

`references/` no se ejecuta en produccion.

| Ruta | Contenido |
| --- | --- |
| `references/planta/plc_reader_y_app/` | Codigo real anterior de planta usado como referencia para tags, handshake y datos historicos. |
| `references/diseno/instrucciones/` | Material visual y pantallas de referencia de la UI. |
| `references/modelos_legacy/modelo/` | Scripts y artefactos ML anteriores que no son el contrato CleaNet ONNX actual. |

## Donde cambiar cada cosa

| Necesidad | Lugar correcto |
| --- | --- |
| Cambiar IP de PLC o estacion | `plc_gateway/mapping.py` |
| Cambiar tags PLC | `plc_gateway/mapping.py` |
| Cambiar ciclo de handshake | `plc_gateway/adapter.py` y pruebas en `tests/test_plc_gateway.py` |
| Cambiar fuente historica del simulador | `simulator.py` o `plc_gateway/sources.py` |
| Cambiar modelo ONNX | `onnx_models/` y `brain/model.py` si cambia el contrato |
| Cambiar UI | `brain/static/` |
| Cambiar consultas o persistencia | `brain/repository.py` |
| Cambiar schema de DB | `db_init/init.sql` y `brain/repository.py::ensure_schema` |
| Cambiar variables de entorno | `.env.example` y `docker-compose.yml` |

## Que no hacer

- No hacer que `brain` lea PLC directamente.
- No importar codigo desde `references/planta/plc_reader_y_app/`.
- No usar `PalletId` como identificador unico de pasada.
- No quitar el limite de historial sin reemplazarlo por otro esquema de conteo eficiente.
- No mover `onnx_models/` sin actualizar el volumen en `docker-compose.yml`.
- No mezclar scripts legacy de `references/modelos_legacy/` con el contrato ONNX actual.

## Verificacion despues de cambios

Minimo:

```bash
python3 -m unittest
```

Para cambios de UI/API:

```bash
docker compose up --build -d
python3 simulator.py --limit 100
curl http://localhost:8000/api/dashboard
```

Para cambios PLC:

```bash
python3 simulator.py --limit 100
python3 plc_adapter.py --broker <IP_BROKER>
```

La primera prueba confirma el contrato simulado. La segunda debe hacerse solo en entorno con PLC real o banco de pruebas.
