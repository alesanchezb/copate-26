"""Inference hook for the production ML model.

Each (real_station, schedule) pair can register a (model, scaler) trained on the
five PLC features the simulator emits: distancia, fuerza, ampers, volts, watts.
Models are loaded lazily on first use and cached. If no model is registered for
the incoming event the function returns None so the temporary rule fallback in
`repository.evaluate_detection` keeps running.

Models are expected to be scikit-learn IsolationForest instances (predict
returns 1 for inlier / -1 for outlier) paired with a scaler that exposes
`transform`. That mirrors the training script the data-science team ships under
`modelo/predecir_est140 (1).py`.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any


MODEL_DIR = Path(os.environ.get("MODEL_DIR", "/app/modelo"))
FEATURE_ORDER = ("distancia", "fuerza", "ampers", "volts", "watts")

# Registry: (real_station, schedule) -> (model_filename, scaler_filename).
# Only the combos with shipped artefacts go here; everything else falls through
# to the rule fallback.
_REGISTRY: dict[tuple[str, str], tuple[str, str]] = {
    ("140", "Sch1"): ("modelo_iso_est140Sch1.pkl", "scaler_est140Sch1.pkl"),
}

_log = logging.getLogger(__name__)
_cache: dict[tuple[str, str], tuple[Any, Any] | None] = {}
_lock = threading.Lock()


def _load_artefacts(real_station: str, schedule: str) -> tuple[Any, Any] | None:
    key = (real_station, schedule)
    if key in _cache:
        return _cache[key]

    with _lock:
        if key in _cache:
            return _cache[key]

        entry = _REGISTRY.get(key)
        if entry is None:
            _cache[key] = None
            return None

        model_path = MODEL_DIR / entry[0]
        scaler_path = MODEL_DIR / entry[1]

        try:
            import joblib  # imported lazily so tests without sklearn still load
        except ImportError as exc:
            _log.warning("joblib no disponible, modelo deshabilitado: %s", exc)
            _cache[key] = None
            return None

        try:
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
        except FileNotFoundError as exc:
            _log.warning("Artefacto faltante para %s: %s", key, exc)
            _cache[key] = None
            return None
        except Exception as exc:
            _log.exception("Fallo cargando modelo %s: %s", key, exc)
            _cache[key] = None
            return None

        _cache[key] = (model, scaler)
        return _cache[key]


def _features_from_event(event: dict[str, Any]) -> list[float] | None:
    values = []
    for name in FEATURE_ORDER:
        raw = event.get(name)
        if raw is None:
            return None
        try:
            values.append(float(raw))
        except (TypeError, ValueError):
            return None
    return values


def _normalize_score(decision_value: float) -> float:
    """Map IsolationForest decision_function to a [0, 0.99] anomaly score.

    decision_function is positive for inliers and negative for outliers, with
    typical magnitude around 0.0 - 0.3. The mapping keeps 0.5 at the boundary.
    """
    raw = 0.5 - decision_value * 1.5
    return max(0.0, min(0.99, raw))


def predict(event: dict[str, Any]) -> dict[str, Any] | None:
    real_station = event.get("real_station")
    schedule = event.get("schedule")
    if not real_station or not schedule:
        return None

    artefacts = _load_artefacts(str(real_station), str(schedule))
    if artefacts is None:
        return None

    features = _features_from_event(event)
    if features is None:
        return None

    model, scaler = artefacts

    import warnings

    import numpy as np

    x = np.array([features])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            x_scaled = scaler.transform(x)
            label = int(model.predict(x_scaled)[0])
            try:
                decision = float(model.decision_function(x_scaled)[0])
            except AttributeError:
                decision = -0.2 if label == -1 else 0.2
        except Exception as exc:
            _log.exception(
                "Fallo de inferencia (%s, %s): %s", real_station, schedule, exc
            )
            return None

    is_anomaly = label == -1
    score = _normalize_score(decision)

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "confidence": score if is_anomaly else max(0.0, 1.0 - score),
        "source": f"isolation_forest_{real_station}_{schedule}",
        "reason": (
            f"IsolationForest marca anomalia (score {score:.2f}, df {decision:.3f})"
            if is_anomaly
            else f"IsolationForest nominal (score {score:.2f}, df {decision:.3f})"
        ),
    }
