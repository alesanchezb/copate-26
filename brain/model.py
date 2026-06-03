"""CleaNet ONNX inference hook.

The production contract is intentionally stable: callers pass a normalized weld
event and receive a small detection dict. The concrete model files can change as
long as they keep the CleaNet metadata shape documented in ``onnx_models/doc.md``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any


ONNX_MODEL_DIR = Path(os.environ.get("ONNX_MODEL_DIR", "/app/onnx_models"))

BASE_FEATURES = ("distancia", "fuerza", "ampers", "volts", "watts")
MODEL_FEATURES = (
    "distancia",
    "watts",
    "distancia_delta",
    "fuerza_delta",
    "watts_delta",
)
CLAMP_FEATURES = ("distancia_delta", "fuerza_delta", "watts_delta")

_log = logging.getLogger(__name__)
_sessions: dict[str, dict[str, Any]] | None = None
_clamps: dict[str, dict[str, float]] | None = None
_last_weld_by_group: dict[tuple[str, str], dict[str, float]] = {}
_load_lock = threading.Lock()
_buffer_lock = threading.Lock()


def _model_key(real_station: object, schedule: object) -> str:
    return f"{str(real_station).strip()}_{str(schedule).strip()}"


def _load_runtime() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]]] | None:
    global _sessions, _clamps
    if _sessions is not None and _clamps is not None:
        return _sessions, _clamps

    with _load_lock:
        if _sessions is not None and _clamps is not None:
            return _sessions, _clamps

        try:
            import onnxruntime as ort
        except ImportError as exc:
            _log.warning("onnxruntime no disponible, modelo CleaNet deshabilitado: %s", exc)
            _sessions = {}
            _clamps = {}
            return None

        clamps_path = ONNX_MODEL_DIR / "clamps.json"
        try:
            with clamps_path.open(encoding="utf-8") as file:
                _clamps = json.load(file)
        except FileNotFoundError:
            _log.warning("No existe clamps.json en %s", ONNX_MODEL_DIR)
            _sessions = {}
            _clamps = {}
            return None

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1

        loaded: dict[str, dict[str, Any]] = {}
        for onnx_path in sorted(ONNX_MODEL_DIR.glob("cleanet_*.onnx")):
            key = onnx_path.stem.removeprefix("cleanet_")
            meta_path = ONNX_MODEL_DIR / f"cleanet_{key}_meta.json"
            try:
                with meta_path.open(encoding="utf-8") as file:
                    meta = json.load(file)
                loaded[key] = {
                    "sess": ort.InferenceSession(str(onnx_path), opts),
                    "meta": meta,
                }
                _log.info("Modelo CleaNet cargado: %s", key)
            except Exception as exc:
                _log.exception("No fue posible cargar CleaNet %s: %s", key, exc)

        _sessions = loaded
        return _sessions, _clamps


def _features_from_event(event: dict[str, Any]) -> dict[str, float] | None:
    values: dict[str, float] = {}
    for name in BASE_FEATURES:
        raw = event.get(name)
        if raw is None:
            return None
        try:
            values[name] = float(raw)
        except (TypeError, ValueError):
            return None
    return values


def _deltas_for_group(
    group: tuple[str, str],
    current: dict[str, float],
) -> dict[str, float]:
    with _buffer_lock:
        previous = _last_weld_by_group.get(group)
        if previous is None:
            deltas = {
                "distancia_delta": 0.0,
                "fuerza_delta": 0.0,
                "watts_delta": 0.0,
            }
        else:
            deltas = {
                "distancia_delta": current["distancia"] - previous["distancia"],
                "fuerza_delta": current["fuerza"] - previous["fuerza"],
                "watts_delta": current["watts"] - previous["watts"],
            }
        _last_weld_by_group[group] = current.copy()
    return deltas


def _apply_clamps(
    deltas: dict[str, float],
    clamps: dict[str, dict[str, float]],
) -> dict[str, float]:
    clamped = deltas.copy()
    for name in CLAMP_FEATURES:
        bounds = clamps.get(name)
        if not bounds:
            continue
        low = float(bounds["low"])
        high = float(bounds["high"])
        clamped[name] = min(max(float(clamped[name]), low), high)
    return clamped


def _classify(score: float, thresholds: dict[str, float]) -> tuple[str, int]:
    if score <= thresholds["p90"]:
        return "BUENA", 0
    if score <= thresholds["p95"]:
        return "POSIBLE_BUENA", 1
    if score <= thresholds["p99"]:
        return "POSIBLE_MALA", 2
    return "MALA", 3


def _confidence_for_level(level_num: int) -> float:
    return {
        0: 0.9,
        1: 0.7,
        2: 0.82,
        3: 0.95,
    }.get(level_num, 0.5)


def predict(event: dict[str, Any]) -> dict[str, Any] | None:
    real_station = event.get("real_station")
    schedule = event.get("schedule")
    if not real_station or not schedule:
        return None

    runtime = _load_runtime()
    if runtime is None:
        return None

    sessions, clamps = runtime
    requested_key = _model_key(real_station, schedule)
    model_key = requested_key
    model_entry = sessions.get(model_key)
    if model_entry is None:
        return None

    current = _features_from_event(event)
    if current is None:
        return None

    deltas = _apply_clamps(
        _deltas_for_group((str(real_station), str(schedule)), current),
        clamps,
    )

    try:
        import numpy as np

        x_raw = np.array(
            [
                [
                    current["distancia"],
                    current["watts"],
                    deltas["distancia_delta"],
                    deltas["fuerza_delta"],
                    deltas["watts_delta"],
                ]
            ],
            dtype=np.float32,
        )

        meta = model_entry["meta"]
        mean = np.array(meta["scaler"]["mean"], dtype=np.float32)
        scale = np.array(meta["scaler"]["scale"], dtype=np.float32)
        x_scaled = ((x_raw - mean) / scale).astype(np.float32)
        recon, _ = model_entry["sess"].run(None, {"input": x_scaled})
        score = float(((x_scaled - recon) ** 2).mean())
    except Exception as exc:
        _log.exception("Fallo de inferencia CleaNet (%s): %s", model_key, exc)
        return None

    level, level_num = _classify(score, model_entry["meta"]["thresholds"])
    is_anomaly = level_num >= 2
    source = f"cleanet_{model_key}"

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "confidence": _confidence_for_level(level_num),
        "source": source,
        "reason": f"CleaNet {level} (score {score:.6f}, modelo {model_key})",
        "model_key": model_key,
        "model_level": level,
        "model_level_num": level_num,
        "model_score": score,
        "model_is_fallback": False,
    }
