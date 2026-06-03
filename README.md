# Sistema de Alertas de Soldadura

Aplicacion de monitoreo en tiempo real para una celda industrial de soldadura de busbars. El proyecto esta preparado para operar de dos formas:

- En desarrollo: con `simulator.py`, que reproduce datos historicos reales usando tags y handshake tipo PLC.
- En planta: con `plc_adapter.py`, que lee los PLC reales con `pylogix` y publica el mismo contrato MQTT que consume `brain`.

La interfaz queda disponible en `http://localhost:8000`.

## Estructura del proyecto

```text
brain/                 Servicio FastAPI, consumidor MQTT, alertas, UI y persistencia
plc_gateway/           Frontera PLC/MQTT compartida por simulador y adapter real
simulator.py           Emisor local con PLC simulado e historico real
plc_adapter.py         Emisor para PLC real en planta
db_init/               Inicializacion de PostgreSQL
mosquitto/             Configuracion del broker MQTT
onnx_models/           Modelos CleaNet ONNX montados read-only en Docker
data/                  Fuente historica local primaria del simulador
docs/                  Manuales de usuario, planta y operacion
references/            Material de referencia que no se ejecuta en produccion
tests/                 Pruebas unitarias
```

`references/planta/plc_reader_y_app/` conserva el codigo que si se uso como referencia real de maquila. No es una dependencia directa del programa nuevo; sirve para auditoria, comparacion de tags y respaldo historico.

## Flujo de datos

```text
PLC real o simulador
  -> lee tags NewData/ForceLast/DistLast/AmpsLast/VoltsLast/WattsLast/ElctCtr/PalletId
  -> adapter MQTT normaliza evento
  -> topic fabrica/linea1/soldadura
  -> brain consume MQTT
  -> modelo CleaNet o rule_fallback conservador
  -> PostgreSQL
  -> UI web y APIs
```

`brain` no lee tags PLC directamente. Esa separacion es intencional: en planta solo se cambia el emisor (`plc_adapter.py`), no la UI, la base de datos ni el motor de alertas.

## Requisitos

- Docker con `docker compose`
- Python 3.10 o superior
- `uv` recomendado para el entorno Python local
- Para PLC real: acceso de red a los PLC y `pylogix` instalado en el equipo que ejecuta `plc_adapter.py`

## Configuracion inicial

```bash
cp .env.example .env
docker compose up --build -d
```

Servicios esperados:

- `broker`: Mosquitto MQTT en puerto `1883`
- `db`: PostgreSQL en puerto `5432`
- `cerebro`: API/UI en puerto `8000`

Revisar estado:

```bash
docker compose ps
docker compose logs -f broker db cerebro
```

## Ejecutar con simulador

Crear entorno Python:

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

En Windows PowerShell:

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

Ejecutar:

```bash
python3 simulator.py
```

Opciones utiles:

```bash
python3 simulator.py --limit 100
python3 simulator.py --speed 8
python3 simulator.py --timestamp-mode historical
```

Fuente historica del simulador:

1. `data/WeldParameters.db`
2. `references/planta/plc_reader_y_app/WeldParameters.db`
3. `references/planta/plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv`

## Ejecutar con PLC real

Instalar dependencia solo en el equipo lector del PLC:

```bash
uv pip install "pylogix>=1.0.5"
```

Con Docker levantado y el broker disponible:

```bash
python3 plc_adapter.py --broker localhost --topic fabrica/linea1/soldadura
```

En planta, `--broker` debe apuntar al host donde corre Mosquitto. El adapter usa el mapeo actual:

- `172.16.14.1`: estaciones reales `140` y `145`
- `172.16.15.1`: estaciones reales `150` y `155`
- `Sch1`: primera soldadura de la estacion
- `Sch2`: segunda soldadura de la estacion

Mas detalle en `docs/IMPLEMENTACION_PLC_PLANTA.md`.

## Verificacion

Pruebas unitarias:

```bash
python3 -m unittest
```

Smoke local:

```bash
docker compose up --build -d
python3 simulator.py --limit 100
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dashboard
```

Luego abrir:

```text
http://localhost:8000
```

## Documentacion principal

- `docs/MANUAL_USUARIO.md`: operacion diaria, pantallas y respuesta ante alertas.
- `docs/IMPLEMENTACION_PLC_PLANTA.md`: pasos para instalar el adapter real en planta.
- `docs/ESTRUCTURA_PROYECTO.md`: que carpeta se ejecuta, que carpeta es referencia y que no tocar.
- `ARQUITECTURA_PROYECTO.md`: contrato tecnico y decisiones de arquitectura.

## Notas importantes

- `PalletId` del PLC identifica un pallet fisico reutilizable; no representa una pasada unica.
- La UI, detalle e inferencia agrupan por `pallet_run_id`.
- `PalletId` 0 o negativo se conserva como dato normal.
- Si no hay modelo exacto para una combinacion `{real_station}_{schedule}`, `brain/model.py` regresa `None` y se usa `rule_fallback`.
- El fallback solo marca `MALO` cuando `ampers > 13.5` o `volts < 1.8` con score `>= 0.5`.
