# CleaNet — Documentación de inferencia ONNX

## ¿Qué hace el modelo?

CleaNet es un **autoencoder** entrenado por estación y esquema de soldadura.
Aprende a reconstruir el patrón de una soldadura normal.
Cuando recibe una soldadura inusual, la reconstrucción es mala → el **score de error** sube → se clasifica como anomalía.

No necesita etiquetas de "buena/mala" para entrenarse: aprende solo el patrón normal.

---

## Archivos por modelo

| Archivo | Contenido |
|---|---|
| `cleanet_{key}.onnx` | Pesos del modelo exportados |
| `cleanet_{key}_meta.json` | Features, scaler, umbrales de clasificación, límites de clamp |

donde `key` = `{estacion}_{esquema}`, por ejemplo `150_Sch1`.

---

## Pipeline completo de preprocesamiento

Antes de llamar al modelo, los datos **crudos** deben pasar por 3 pasos en orden.
El modelo recibe la salida del paso 3.

```
datos crudos (distancia, fuerza, ampers, volts, watts)
        │
        ▼  paso 1 — agregar_features_temporales_v3()
datos + deltas (distancia_delta, fuerza_delta, watts_delta, ...)
        │
        ▼  paso 2 — aplicar_clamp()   ← usar límites de TRAIN, no recalcular
datos con deltas clampeados
        │
        ▼  paso 3 — seleccionar FEATURES_V3 y pasar a inferencia_onnx()
[distancia, watts, distancia_delta, fuerza_delta, watts_delta]
        │
        ▼
      modelo
```

### Paso 1 — Calcular deltas (`agregar_features_temporales_v3`)

```python
BASE_FEATURES = ['distancia', 'fuerza', 'ampers', 'volts', 'watts']
data = agregar_features_temporales_v3(data, BASE_FEATURES)
```

Esta función agrega una columna `{feature}_delta` para cada feature de entrada,
calculada como la **diferencia respecto a la soldadura anterior** dentro del mismo
grupo `(estacion, sch)`, ordenado por `timestamp`.

| Columna generada | Fórmula |
|---|---|
| `distancia_delta` | `distancia[t] - distancia[t-1]` |
| `fuerza_delta` | `fuerza[t] - fuerza[t-1]` |
| `ampers_delta` | `ampers[t] - ampers[t-1]` |
| `volts_delta` | `volts[t] - volts[t-1]` |
| `watts_delta` | `watts[t] - watts[t-1]` |

> Para la primera soldadura de cada grupo `(estacion, sch)`, el delta es `0`
> (no hay soldadura anterior con qué comparar).

**Requisitos del DataFrame de entrada:**

| Columna | Tipo | Descripción |
|---|---|---|
| `estacion` | int | ID de la estación |
| `sch` | str | Esquema (`Sch1`, `Sch2`, ...) |
| `timestamp` | datetime / int | Marca de tiempo para ordenar |
| `distancia` | float | Distancia de soldadura (mm) |
| `fuerza` | float | Fuerza aplicada (N) |
| `ampers` | float | Corriente (A) |
| `volts` | float | Voltaje (V) |
| `watts` | float | Potencia (W) |

---

### Paso 2 — Aplicar clamp (`aplicar_clamp`)

```python
data = aplicar_clamp(data, clamps)
```

Los deltas pueden tener outliers extremos que distorsionan el modelo.
El clamp recorta los valores fuera del rango `[p1, p99]` calculado sobre train.

> ⚠️ **Los límites de clamp se calculan UNA SOLA VEZ sobre el set de entrenamiento**
> con `calcular_clamp_percentiles()` y se reutilizan en producción tal cual.
> Nunca recalcular sobre datos nuevos.

Las 3 columnas que se clampean son:

| Columna | p_low | p_high |
|---|---|---|
| `distancia_delta` | percentil 1 de train | percentil 99 de train |
| `fuerza_delta` | percentil 1 de train | percentil 99 de train |
| `watts_delta` | percentil 1 de train | percentil 99 de train |

Para guardar y reutilizar los límites:

```python
import json

# Guardar (una vez, después de entrenar)
with open('onnx_models/clamps.json', 'w') as f:
    json.dump(clamps, f, indent=2)

# Cargar en producción
with open('onnx_models/clamps.json') as f:
    clamps = json.load(f)

data = aplicar_clamp(data, clamps)
```

---

### Paso 3 — Seleccionar features y llamar al modelo

De todas las columnas disponibles, el modelo usa exactamente estas 5, en este orden:

```python
FEATURES_V3 = ['distancia', 'watts', 'distancia_delta', 'fuerza_delta', 'watts_delta']
```

| # | Feature | Descripción | Tipo |
|:-:|---|---|---|
| 0 | `distancia` | Distancia de soldadura | feature base |
| 1 | `watts` | Potencia instantánea | feature base |
| 2 | `distancia_delta` | Cambio de distancia vs. soldadura anterior (clampeado) | delta |
| 3 | `fuerza_delta` | Cambio de fuerza vs. soldadura anterior (clampeado) | delta |
| 4 | `watts_delta` | Cambio de potencia vs. soldadura anterior (clampeado) | delta |

> `ampers`, `volts`, `ampers_delta` y `volts_delta` se calculan en el paso 1
> pero **no entran al modelo** — no están en `FEATURES_V3`.

---

## Función de inferencia

```python
import json
import numpy as np
import onnxruntime as ort

def inferencia_onnx(onnx_path, meta_path, X_raw):
    """
    Clasifica soldaduras usando el modelo CleaNet exportado a ONNX.

    Parámetros
    ----------
    onnx_path : str
        Ruta al archivo .onnx del modelo.
    meta_path : str
        Ruta al archivo _meta.json con scaler y umbrales.
    X_raw : np.ndarray, shape (N, 5)
        Datos SIN escalar, ya con clamp aplicado. Columnas en orden:
        [distancia, watts, distancia_delta, fuerza_delta, watts_delta]

    Retorna
    -------
    list[dict] con N elementos. Cada dict contiene:
        score      (float) — error de reconstrucción; mayor = más inusual
        nivel      (str)   — clasificación de la pieza
        nivel_num  (int)   — código numérico de clasificación
    """
    with open(meta_path) as f:
        meta = json.load(f)

    mean  = np.array(meta['scaler']['mean'],  dtype=np.float32)
    scale = np.array(meta['scaler']['scale'], dtype=np.float32)
    X_scaled = ((X_raw - mean) / scale).astype(np.float32)

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1   # evita warnings de afinidad de threads
    opts.inter_op_num_threads = 1

    sess = ort.InferenceSession(onnx_path, opts)
    recon, _ = sess.run(None, {'input': X_scaled})

    scores = ((X_scaled - recon) ** 2).mean(axis=1)

    th = meta['thresholds']
    resultados = []
    for score in scores:
        if   score <= th['p90']: nivel, nivel_num = 'BUENA',         0
        elif score <= th['p95']: nivel, nivel_num = 'POSIBLE_BUENA', 1
        elif score <= th['p99']: nivel, nivel_num = 'POSIBLE_MALA',  2
        else:                    nivel, nivel_num = 'MALA',          3

        resultados.append({
            'score':     float(score),
            'nivel':     nivel,
            'nivel_num': nivel_num,
        })

    return resultados
```

### Ejemplo completo de uso en producción

```python
import pandas as pd
import numpy as np
import json

# Fucniones auxiliares
def agregar_features_temporales_v3(df, features, ventana=5):
    """
    Solo deltas. Sin rzscore. Sin Electrodecount.
    Clamp por percentiles calculados dentro de cada grupo (est, sch)
    para que train y test sean comparables.
    """
    df = df.sort_values(['estacion', 'sch', 'timestamp']).copy()

    for f in features:
        grp = df.groupby(['estacion', 'sch'])[f]
        df[f'{f}_delta'] = grp.diff().fillna(0)

    # Clamp por percentiles GLOBALES de train — aplicar mismo clamp a test
    # Se hace fuera de esta función para usar los percentiles de train
    df = df.fillna(0)
    return df


def calcular_clamp_percentiles(data_df, delta_features, p_low=1, p_high=99):
    """Calcula los percentiles de clamp sobre train solamente."""
    clamps = {}
    for f in delta_features:
        clamps[f] = {
            'low':  data_df[f].quantile(p_low  / 100),
            'high': data_df[f].quantile(p_high / 100),
        }
    return clamps


def aplicar_clamp(df, clamps):
    """Aplica los mismos clamps (calculados en train) a cualquier df."""
    df = df.copy()
    for f, bounds in clamps.items():
        df[f] = df[f].clip(bounds['low'], bounds['high'])
    return df

# 1. Cargar límites de clamp guardados de train
with open('onnx_models/clamps.json') as f:
    clamps = json.load(f)

# 2. Datos nuevos (mínimo: estacion, sch, timestamp + BASE_FEATURES)
nuevas = pd.DataFrame([
    {'estacion': 150, 'sch': 'Sch1', 'timestamp': 1,
     'distancia': 0.35, 'fuerza': 5.1, 'ampers': 12.0, 'volts': 0.6, 'watts': 7.2},
    {'estacion': 150, 'sch': 'Sch1', 'timestamp': 2,
     'distancia': 0.40, 'fuerza': 5.3, 'ampers': 12.1, 'volts': 0.6, 'watts': 9.5},
])

# 3. Preprocesamiento
BASE_FEATURES = ['distancia', 'fuerza', 'ampers', 'volts', 'watts']
FEATURES_V3   = ['distancia', 'watts', 'distancia_delta', 'fuerza_delta', 'watts_delta']

nuevas = agregar_features_temporales_v3(nuevas, BASE_FEATURES)
nuevas = aplicar_clamp(nuevas, clamps)

X_raw = nuevas[FEATURES_V3].values.astype(np.float32)

# 4. Inferencia
resultados = inferencia_onnx(
    onnx_path='onnx_models/cleanet_150_Sch1.onnx',
    meta_path='onnx_models/cleanet_150_Sch1_meta.json',
    X_raw=X_raw
)

for r in resultados:
    print(f"score={r['score']:.5f}  →  {r['nivel']}")
```

---

## Clasificación de la pieza

| nivel_num | nivel | Criterio | Acción sugerida |
|:-:|---|---|---|
| 0 | `BUENA` | score ≤ p90 | Aprobar |
| 1 | `POSIBLE_BUENA` | p90 < score ≤ p95 | Aprobar con registro |
| 2 | `POSIBLE_MALA` | p95 < score ≤ p99 | Revisión manual |
| 3 | `MALA` | score > p99 | Rechazar / inspeccionar |

Los umbrales p90/p95/p99 están calculados sobre el set de entrenamiento de cada
estación y esquema. **No son intercambiables entre modelos.**

---

## Un modelo por estación/esquema

```
onnx_models/
├── clamps.json                   ← límites de clamp (compartido por todos)
├── cleanet_150_Sch1.onnx
├── cleanet_150_Sch1_meta.json
├── cleanet_155_Sch2.onnx
└── cleanet_155_Sch2_meta.json
```

Seleccionar el par `(.onnx, _meta.json)` que corresponde a la estación y esquema
de la soldadura a evaluar.

---

## Instalación mínima en producción

```bash
pip install onnxruntime numpy pandas
```

PyTorch **no es necesario** en producción.

---

## Uso en tiempo real (producción)

### El problema de los deltas

Los deltas (`distancia_delta`, `fuerza_delta`, `watts_delta`) se calculan como
la diferencia contra la **soldadura inmediatamente anterior** del mismo grupo
`(estacion, sch)`. En producción, las soldaduras llegan de una en una, por lo que
no es posible usar `agregar_features_temporales_v3` — esa función opera sobre
un DataFrame completo.

La solución es mantener un **buffer en memoria** con la última soldadura vista
por cada grupo `(estacion, sch)`.

```
arranque del proceso
        │
        ▼  cargar_sessions()  ← una sola vez
modelos + clamps en memoria
        │
        │   por cada soldadura nueva que llega:
        ▼
inferencia_realtime(estacion, sch, soldadura, clamps, sessions)
        │
        ├─ leer última soldadura del buffer  (o delta=0 si es la primera)
        ├─ calcular deltas
        ├─ aplicar clamp
        ├─ escalar con StandardScaler del meta.json
        ├─ correr modelo ONNX
        ├─ calcular score y clasificar
        └─ actualizar buffer con la soldadura actual
        │
        ▼
{'score': float, 'nivel': str, 'nivel_num': int}
```

### Inicialización — cargar todo al arrancar

```python
import glob, json
import numpy as np
import onnxruntime as ort

def cargar_sessions(directory='onnx_models'):
    """
    Carga todos los modelos y el archivo de clamps en memoria.
    Llamar UNA SOLA VEZ al inicio del proceso.

    Retorna
    -------
    sessions : dict  key -> {'sess': InferenceSession, 'meta': dict}
    clamps   : dict  feature -> {'low': float, 'high': float}
    """
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1

    with open(f'{directory}/clamps.json') as f:
        clamps = json.load(f)

    sessions = {}
    for onnx_path in glob.glob(f'{directory}/cleanet_*.onnx'):
        key       = onnx_path.split('cleanet_')[1].replace('.onnx', '')
        meta_path = onnx_path.replace('.onnx', '_meta.json')
        with open(meta_path) as f:
            meta = json.load(f)
        sessions[key] = {
            'sess': ort.InferenceSession(onnx_path, opts),
            'meta': meta,
        }
        print(f'✓ modelo cargado: {key}')

    return sessions, clamps
```

### Inferencia soldadura a soldadura

```python
# Buffer global — persiste entre llamadas, una entrada por (estacion, sch)
_ultima_soldadura = {}

def inferencia_realtime(estacion, sch, soldadura_actual, clamps, sessions):
    """
    Clasifica una soldadura individual en tiempo real.

    Parámetros
    ----------
    estacion        : int   — ID de la estación (ej. 150)
    sch             : str   — esquema (ej. 'Sch1')
    soldadura_actual: dict  — valores crudos de la soldadura:
                              {'distancia': float, 'fuerza': float,
                               'ampers': float, 'volts': float, 'watts': float}
    clamps          : dict  — límites de clamp cargados de clamps.json
    sessions        : dict  — sesiones ONNX cargadas con cargar_sessions()

    Retorna
    -------
    dict con:
        score      (float) — error de reconstrucción
        nivel      (str)   — 'BUENA' | 'POSIBLE_BUENA' | 'POSIBLE_MALA' | 'MALA'
        nivel_num  (int)   — 0 | 1 | 2 | 3
    """
    key      = f'{estacion}_{sch}'
    anterior = _ultima_soldadura.get(key)

    # Calcular deltas (0 si es la primera soldadura del grupo)
    if anterior is None:
        distancia_delta = fuerza_delta = watts_delta = 0.0
    else:
        distancia_delta = soldadura_actual['distancia'] - anterior['distancia']
        fuerza_delta    = soldadura_actual['fuerza']    - anterior['fuerza']
        watts_delta     = soldadura_actual['watts']     - anterior['watts']

    # Actualizar buffer antes de cualquier error posible
    _ultima_soldadura[key] = soldadura_actual.copy()

    # Aplicar clamp con los límites de train
    distancia_delta = np.clip(distancia_delta,
                              clamps['distancia_delta']['low'],
                              clamps['distancia_delta']['high'])
    fuerza_delta    = np.clip(fuerza_delta,
                              clamps['fuerza_delta']['low'],
                              clamps['fuerza_delta']['high'])
    watts_delta     = np.clip(watts_delta,
                              clamps['watts_delta']['low'],
                              clamps['watts_delta']['high'])

    # Vector de entrada: [distancia, watts, distancia_delta, fuerza_delta, watts_delta]
    X_raw = np.array([[
        soldadura_actual['distancia'],
        soldadura_actual['watts'],
        distancia_delta,
        fuerza_delta,
        watts_delta,
    ]], dtype=np.float32)

    # Escalar con el StandardScaler del modelo
    s     = sessions[key]
    mean  = np.array(s['meta']['scaler']['mean'],  dtype=np.float32)
    scale = np.array(s['meta']['scaler']['scale'], dtype=np.float32)
    X_scaled = (X_raw - mean) / scale

    # Inferencia ONNX
    recon, _ = s['sess'].run(None, {'input': X_scaled})
    score    = float(((X_scaled - recon) ** 2).mean())

    # Clasificar
    th = s['meta']['thresholds']
    if   score <= th['p90']: nivel, nivel_num = 'BUENA',         0
    elif score <= th['p95']: nivel, nivel_num = 'POSIBLE_BUENA', 1
    elif score <= th['p99']: nivel, nivel_num = 'POSIBLE_MALA',  2
    else:                    nivel, nivel_num = 'MALA',          3

    return {'score': score, 'nivel': nivel, 'nivel_num': nivel_num}
```

### Ejemplo de uso en un loop de producción

```python
# Al arrancar el servicio
sessions, clamps = cargar_sessions('onnx_models')

# Simulación de soldaduras llegando en tiempo real
soldaduras_stream = [
    {'estacion': 150, 'sch': 'Sch1',
     'distancia': 0.35, 'fuerza': 5.1, 'ampers': 12.0, 'volts': 0.6, 'watts': 7.2},
    {'estacion': 150, 'sch': 'Sch1',
     'distancia': 0.40, 'fuerza': 5.3, 'ampers': 12.1, 'volts': 0.6, 'watts': 9.5},
    {'estacion': 155, 'sch': 'Sch2',
     'distancia': 0.38, 'fuerza': 4.9, 'ampers': 11.8, 'volts': 0.6, 'watts': 7.0},
]

for s in soldaduras_stream:
    resultado = inferencia_realtime(
        estacion        = s['estacion'],
        sch             = s['sch'],
        soldadura_actual = {k: s[k] for k in ['distancia','fuerza','ampers','volts','watts']},
        clamps          = clamps,
        sessions        = sessions,
    )
    print(f"Est {s['estacion']} {s['sch']} → {resultado['nivel']}  (score={resultado['score']:.5f})")
```

### Consideraciones importantes

**Reinicio del buffer:** Si el proceso se reinicia o hay un corte en la línea,
`_ultima_soldadura` se vacía y la siguiente soldadura tendrá `delta = 0`.
Esto es el mismo comportamiento que al inicio del turno — aceptable para una
soldadura, no para un reinicio frecuente.

**Multi-estación simultánea:** El buffer `_ultima_soldadura` está indexado por
`key = f'{estacion}_{sch}'`, por lo que múltiples estaciones operando en paralelo
son manejadas correctamente sin conflicto.

**Thread safety:** Si múltiples threads llaman a `inferencia_realtime` en paralelo
para la misma `(estacion, sch)`, puede haber condición de carrera en el buffer.
Solución: usar un `threading.Lock` por key, o procesar cada estación en su propio thread.
