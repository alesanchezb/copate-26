# Implementacion en planta con PLC real

## Objetivo

Esta guia explica como pasar del simulador a datos reales de PLC sin cambiar `brain`, la UI ni la base de datos. La unica pieza que cambia es el emisor de telemetria:

```text
simulator.py  -> desarrollo
plc_adapter.py -> planta
```

Ambos publican el mismo contrato MQTT.

## Requisitos de red

El equipo que ejecuta `plc_adapter.py` debe tener:

- Acceso TCP/IP al broker MQTT.
- Acceso EtherNet/IP a los PLC reales.
- Puerto `44818` disponible hacia los PLC Allen-Bradley.
- Python 3.10 o superior.
- Paquete `pylogix`.

PLCs configurados actualmente:

| PLC | Estaciones reales | Slots locales |
| --- | --- | --- |
| `172.16.14.1` | `140`, `145` | `St1`, `St2` |
| `172.16.15.1` | `150`, `155` | `St1`, `St2` |

## Tags esperados

Por cada combinacion `Sch1/Sch2` y `St1/St2`:

| Funcion | Patron |
| --- | --- |
| Bandera de nueva lectura | `NewData{Sch}St{i}` |
| Handshake / ack | `NewData{Sch}St{i}HndShk` |
| Fuerza | `ForceLast{Sch}St{i}` |
| Distancia | `DistLast{Sch}St{i}` |
| Amperaje | `AmpsLast{Sch}St{i}` |
| Voltaje | `VoltsLast{Sch}St{i}` |
| Watts | `WattsLast{Sch}St{i}` |
| Electrodos | `ElctCtr{Sch}St{i}` |
| Pallet | `PalletId{Sch}St{i}` |

Ejemplo para `Sch1` en `St1`:

```text
NewDataSch1St1
ForceLastSch1St1
DistLastSch1St1
AmpsLastSch1St1
VoltsLastSch1St1
WattsLastSch1St1
ElctCtrSch1St1
PalletIdSch1St1
NewDataSch1St1HndShk
```

## Ciclo de lectura

1. El PLC sube `NewData{Sch}St{i}` a `1`.
2. El adapter lee todos los valores de ese slot.
3. El adapter publica el evento normalizado a MQTT.
4. El adapter escribe `NewData{Sch}St{i}HndShk = 1`.
5. Espera `0.25 s`.
6. El adapter escribe `NewData{Sch}St{i}HndShk = 0`.
7. El PLC puede bajar o reciclar la bandera segun su logica.

El adapter evita publicar dos veces la misma bandera mientras siga en `1`.

## Instalacion del adapter

Desde la raiz del proyecto:

```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install "pylogix>=1.0.5"
```

En Windows PowerShell:

```powershell
uv venv
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
uv pip install "pylogix>=1.0.5"
```

## Arranque

Si el broker corre en el mismo equipo:

```bash
python3 plc_adapter.py --broker localhost
```

Si el broker corre en otro servidor:

```bash
python3 plc_adapter.py --broker <IP_O_HOST_DEL_BROKER>
```

Parametros utiles:

```bash
python3 plc_adapter.py \
  --broker <IP_O_HOST_DEL_BROKER> \
  --port 1883 \
  --topic fabrica/linea1/soldadura \
  --line-id linea1 \
  --poll-interval 0.1 \
  --handshake-pulse 0.25
```

## Validacion inicial

1. Levantar infraestructura:

```bash
docker compose up --build -d
```

2. Confirmar salud de API:

```bash
curl http://localhost:8000/api/health
```

3. Ejecutar adapter:

```bash
python3 plc_adapter.py --broker localhost
```

4. Revisar logs:

```bash
docker compose logs -f cerebro
```

Debe aparecer procesamiento de eventos. En la UI el indicador de flujo debe pasar a `PLC activo`.

## Checklist antes de liberar en planta

- Los PLC responden por red desde el equipo del adapter.
- Los tags existen con los nombres esperados.
- `NewData...` cambia a `1` cuando hay lectura nueva.
- El handshake `...HndShk` puede escribirse desde el equipo del adapter.
- El broker MQTT recibe en `fabrica/linea1/soldadura`.
- `brain` no reporta errores de normalizacion.
- La UI muestra `station_1` a `station_4` con welds `1` a `8`.
- `PalletId` se ve igual que en PLC, incluyendo `0` o valores negativos si aparecen.
- `pallet_run_id` cambia por pasada y permite abrir detalle sin mezclar pasadas anteriores.

## Que hacer si no llegan datos

1. Probar conectividad al PLC:

```bash
ping 172.16.14.1
ping 172.16.15.1
```

2. Validar que el puerto industrial responda:

```bash
nc -vz 172.16.14.1 44818
nc -vz 172.16.15.1 44818
```

3. Revisar que el broker este arriba:

```bash
docker compose ps broker
docker compose logs --tail=100 broker
```

4. Revisar logs del adapter. Si aparecen lecturas fallidas de tags, confirmar nombres y permisos de escritura.

## Cambios que requieren desarrollo

Requieren cambio en codigo y pruebas:

- Cambiar IPs de PLC.
- Agregar estaciones.
- Cambiar nombres de tags.
- Cambiar handshake.
- Cambiar significado de `Sch1` o `Sch2`.
- Usar otro topic MQTT.

El lugar correcto para cambios de mapeo es `plc_gateway/mapping.py`. Despues de cualquier cambio se debe ejecutar:

```bash
python3 -m unittest
```

## Relacion con el codigo viejo de planta

El codigo en `references/planta/plc_reader_y_app/` se conserva para consulta. La implementacion nueva no lo importa ni lo ejecuta.

La equivalencia importante es:

- `monitor_plc` del codigo viejo leia `NewData...`, valores y handshake.
- `PlcMqttAdapter` hace esa misma lectura, pero publica MQTT en vez de guardar directo en SQLite.
- `brain` recibe MQTT y se encarga de DB, alertas y UI.

Esta separacion reduce riesgo en planta porque el lector PLC queda pequeno y reemplazable.
