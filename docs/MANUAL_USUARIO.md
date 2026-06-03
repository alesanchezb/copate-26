# Manual de usuario

## Proposito del sistema

El sistema muestra el estado de la celda de soldadura de busbars en tiempo real. Su objetivo es ayudar al operador y al equipo de calidad a detectar soldaduras `MALO`, revisar el pallet afectado y consultar el historial por estacion, pallet o fecha.

La aplicacion no controla el PLC ni modifica parametros de soldadura. Solo recibe telemetria, evalua el resultado y registra alertas.

## Como entrar

Con el sistema levantado, abrir:

```text
http://localhost:8000
```

En planta, la URL puede cambiar segun el equipo donde este instalado Docker. El responsable de IT o mantenimiento debe proporcionar la IP final.

## Pantalla principal

La pantalla principal muestra:

- Estado de las 4 estaciones.
- Ultima lectura por estacion y schedule.
- Indicador de flujo de datos.
- Logs recientes.
- Alerta activa mas reciente.
- Resumen de soldaduras buenas y malas.

El indicador de flujo puede aparecer como:

- `Simulador activo`: datos locales de prueba.
- `PLC activo`: datos reales de planta.
- `sin flujo`: no han llegado eventos recientes.
- `Esperando datos`: aun no hay registros.

## Que significa BUENO y MALO

`BUENO` significa que la soldadura no fue marcada como anomala por el modelo o por el fallback conservador.

`MALO` significa que la soldadura requiere revision. Puede venir de:

- Modelo CleaNet con nivel `POSIBLE_MALA` o `MALA`.
- Regla fallback temporal cuando no hay modelo exacto y los valores estan claramente fuera de banda.

Una alerta `MALO` no debe interpretarse como diagnostico final automatico. Es una senal para revisar la pieza, el pallet y el contexto de la estacion.

## Atender una alerta

1. Abrir la alerta desde el dashboard o desde historial.
2. Revisar pallet, estacion, weld y schedule.
3. Confirmar si el problema se concentra en una sola soldadura o se repite en el pallet.
4. Revisar los valores de `distancia`, `fuerza`, `ampers`, `volts` y `watts`.
5. Seguir el procedimiento interno de calidad/mantenimiento para liberar, retener o inspeccionar la pieza.

La pantalla de detalle usa `pallet_run_id`, no solo `PalletId`, porque el mismo pallet fisico se reutiliza. Esto evita mezclar pasadas diferentes del mismo pallet.

## Historial

La pantalla de historial permite filtrar por:

- Fecha inicial y final.
- Estacion.
- Estado `BUENO` o `MALO`.
- Pallet o `pallet_run_id`.

El historial tiene limite de conteo para proteger el rendimiento. Si aparece `count_capped`, significa que hay mas de 5000 registros que cumplen el filtro. En ese caso conviene acotar por fecha, estacion o pallet.

## Analitica

La pantalla de analitica resume errores por estacion, schedule y hora. Sirve para detectar concentraciones como:

- Una estacion especifica con mas `MALO`.
- Un schedule con comportamiento distinto al otro.
- Horarios donde aumentan los errores.

## Operacion local con simulador

Para una demostracion o prueba sin PLC:

```bash
docker compose up --build -d
python3 simulator.py
```

Abrir:

```text
http://localhost:8000
```

Detener el simulador con `Ctrl+C`.

## Operacion con PLC real

En planta el operador normalmente no ejecuta comandos. El servicio que lee PLC debe estar corriendo en el equipo asignado:

```bash
python3 plc_adapter.py --broker <IP_BROKER>
```

Si la pantalla queda sin flujo:

1. Revisar que el broker MQTT este arriba.
2. Revisar que `cerebro` este arriba.
3. Revisar que el equipo del adapter tenga red hacia `172.16.14.1` y `172.16.15.1`.
4. Revisar logs del adapter PLC.

## Comandos utiles para soporte

Ver contenedores:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f broker db cerebro
```

Reiniciar backend:

```bash
docker compose restart cerebro
```

Reset local completo:

```bash
docker compose down -v
docker compose up --build -d
```

El reset borra la base PostgreSQL local. Usarlo solo en desarrollo o cuando soporte lo indique.

## Buenas practicas de uso

- No comparar pasadas solo por `PalletId`; usar `pallet_run_id` en detalle.
- No cambiar thresholds del fallback para "hacer aparecer" mas alertas.
- No correr `plc_reader_y_app` como parte del sistema nuevo; esta en `references/` solo como referencia.
- No mover `onnx_models/` sin actualizar `ONNX_MODEL_DIR` o el volumen de Docker.
- Reportar cualquier cambio real de tags PLC antes de operar, porque el adapter depende del contrato de tags.
