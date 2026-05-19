from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from config import (
    DB_CONFIG,
    LINE_ID,
    LINE_LABEL,
    OPERATOR_LINE_LABEL,
    OPERATOR_NAME,
    STATIONS,
    normalize_schedule,
    station_by_code,
    station_by_real_station,
    station_for_weld_id,
    weld_id_for_real_station,
)
from model import predict


HISTORY_COUNT_CAP = 5000

_pool: Any | None = None
_pool_lock = threading.Lock()


def _build_pool() -> Any:
    from psycopg2.pool import ThreadedConnectionPool

    return ThreadedConnectionPool(minconn=1, maxconn=10, **DB_CONFIG)


def _get_pool() -> Any:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _build_pool()
    return _pool


@contextmanager
def get_connection():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            pass
        pool.putconn(conn)


def wait_for_database(max_attempts: int = 30, sleep_seconds: int = 2) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.close()
            return
        except Exception as exc:
            print(
                f"[DB] Intento {attempt}/{max_attempts} sin conexion disponible: {exc}"
            )
            time.sleep(sleep_seconds)
    raise RuntimeError("No fue posible conectar con PostgreSQL.")


def ensure_schema() -> None:
    """Three-phase migration so an old `postgres_data` volume can be upgraded in place.

    Step 1 creates tables if missing using their canonical column set.
    Step 2 adds columns that older deployments may be missing.
    Step 3 creates indexes — this MUST run after step 2 because some indexes
    reference newly added columns (pallet_run_id) that would not exist yet on
    an old volume, aborting the whole transaction.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS stations (
                    station_code   VARCHAR(50) PRIMARY KEY,
                    line_id        VARCHAR(50)  NOT NULL,
                    node_label     VARCHAR(50)  NOT NULL,
                    display_name   VARCHAR(100) NOT NULL,
                    station_order  INTEGER      NOT NULL,
                    weld_start     INTEGER      NOT NULL,
                    weld_end       INTEGER      NOT NULL,
                    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS weld_events (
                    event_id          VARCHAR(64) PRIMARY KEY,
                    line_id           VARCHAR(50)  NOT NULL,
                    station_code      VARCHAR(50)  NOT NULL REFERENCES stations(station_code),
                    pallet_id         VARCHAR(50)  NOT NULL,
                    pallet_run_id     VARCHAR(120),
                    weld_id           INTEGER      NOT NULL,
                    source_type       VARCHAR(30)  NOT NULL,
                    source_timestamp  TIMESTAMPTZ  NOT NULL,
                    received_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    distancia         NUMERIC(8, 3),
                    fuerza            NUMERIC(8, 2),
                    ampers            NUMERIC(8, 2),
                    volts             NUMERIC(8, 2),
                    watts             NUMERIC(8, 2),
                    real_station      VARCHAR(50),
                    schedule          VARCHAR(10),
                    plc_ip            VARCHAR(50),
                    electrode_count   VARCHAR(50),
                    voltaje           NUMERIC(6, 2) NOT NULL,
                    corriente         NUMERIC(8, 2),
                    presion           NUMERIC(6, 2) NOT NULL,
                    tiempo_ms         NUMERIC(8, 2),
                    status            VARCHAR(10)  NOT NULL,
                    is_anomaly        BOOLEAN      NOT NULL,
                    anomaly_score     NUMERIC(6, 4),
                    confidence        NUMERIC(6, 4),
                    detection_source  VARCHAR(50)  NOT NULL,
                    detection_reason  TEXT,
                    raw_payload       JSONB        NOT NULL DEFAULT '{}'::jsonb
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id       VARCHAR(64) PRIMARY KEY,
                    event_id       VARCHAR(64) UNIQUE NOT NULL REFERENCES weld_events(event_id) ON DELETE CASCADE,
                    line_id        VARCHAR(50)  NOT NULL,
                    station_code   VARCHAR(50)  NOT NULL REFERENCES stations(station_code),
                    pallet_id      VARCHAR(50)  NOT NULL,
                    pallet_run_id  VARCHAR(120),
                    weld_id        INTEGER      NOT NULL,
                    status         VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',
                    title          VARCHAR(200) NOT NULL,
                    message        TEXT         NOT NULL,
                    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    resolved_at    TIMESTAMPTZ
                );
                """
            )
            cur.execute(
                """
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS pallet_run_id VARCHAR(120);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS distancia NUMERIC(8, 3);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS fuerza NUMERIC(8, 2);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS ampers NUMERIC(8, 2);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS volts NUMERIC(8, 2);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS watts NUMERIC(8, 2);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS real_station VARCHAR(50);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS schedule VARCHAR(10);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS plc_ip VARCHAR(50);
                ALTER TABLE weld_events ADD COLUMN IF NOT EXISTS electrode_count VARCHAR(50);
                ALTER TABLE alerts ADD COLUMN IF NOT EXISTS pallet_run_id VARCHAR(120);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weld_events_station_time
                    ON weld_events (station_code, source_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_weld_events_line_time
                    ON weld_events (line_id, source_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_weld_events_line_status_time
                    ON weld_events (line_id, status, source_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_weld_events_line_station_time
                    ON weld_events (line_id, station_code, source_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_weld_events_pallet
                    ON weld_events (pallet_id, weld_id);
                CREATE INDEX IF NOT EXISTS idx_weld_events_pallet_run
                    ON weld_events (pallet_run_id, weld_id);
                CREATE INDEX IF NOT EXISTS idx_weld_events_status
                    ON weld_events (status, source_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_status
                    ON alerts (status, created_at DESC);
                """
            )
        conn.commit()


def seed_stations() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            for station in STATIONS:
                cur.execute(
                    """
                    INSERT INTO stations (
                        station_code,
                        line_id,
                        node_label,
                        display_name,
                        station_order,
                        weld_start,
                        weld_end
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (station_code) DO UPDATE SET
                        line_id = EXCLUDED.line_id,
                        node_label = EXCLUDED.node_label,
                        display_name = EXCLUDED.display_name,
                        station_order = EXCLUDED.station_order,
                        weld_start = EXCLUDED.weld_start,
                        weld_end = EXCLUDED.weld_end
                    """,
                    (
                        station.code,
                        LINE_ID,
                        station.node_label,
                        station.display_name,
                        station.station_order,
                        station.weld_start,
                        station.weld_end,
                    ),
                )
        conn.commit()


def parse_event_timestamp(raw_value: Any) -> datetime:
    if raw_value is None:
        return datetime.now(timezone.utc)

    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(raw_value, tz=timezone.utc)

    if isinstance(raw_value, str):
        normalized = raw_value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    raise ValueError(f"Timestamp no soportado: {raw_value!r}")


def number_or_none(raw_value: Any) -> float | None:
    if raw_value is None or raw_value == "":
        return None
    return float(raw_value)


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params", {})
    plc = payload.get("plc") or {}
    real_station = payload.get("real_station") or plc.get("real_station")
    schedule = normalize_schedule(payload.get("schedule") or plc.get("schedule"))

    derived_weld_id = weld_id_for_real_station(real_station, schedule)
    weld_id = int(payload.get("weld_id") or derived_weld_id)
    station = (
        station_by_code(payload.get("station_id", ""))
        or station_by_real_station(real_station)
        or station_for_weld_id(weld_id)
    )
    timestamp = parse_event_timestamp(payload.get("timestamp"))

    ml_result = (
        payload.get("ml_result")
        or payload.get("prediction")
        or payload.get("model_output")
        or {}
    )

    if not ml_result and any(
        key in payload for key in ("is_anomaly", "anomaly_score", "confidence")
    ):
        ml_result = {
            "is_anomaly": payload.get("is_anomaly"),
            "score": payload.get("anomaly_score"),
            "confidence": payload.get("confidence"),
            "reason": payload.get("detection_reason"),
        }

    distancia = number_or_none(params.get("distancia"))
    fuerza = number_or_none(params.get("fuerza"))
    ampers = number_or_none(params.get("ampers"))
    volts = number_or_none(params.get("volts"))
    watts = number_or_none(params.get("watts"))

    voltaje = number_or_none(params.get("voltaje"))
    corriente = number_or_none(params.get("corriente"))
    presion = number_or_none(params.get("presion"))
    tiempo_ms = number_or_none(params.get("tiempo_ms"))

    if voltaje is None:
        voltaje = volts if volts is not None else 0
    if corriente is None:
        corriente = ampers
    if presion is None:
        presion = fuerza if fuerza is not None else 0

    pallet_id = str(payload["pallet_id"])
    pallet_run_id = str(payload.get("pallet_run_id") or pallet_id)
    event_id = payload.get("event_id") or f"{pallet_run_id}-{weld_id}-{int(timestamp.timestamp() * 1000)}"
    electrode_count = (
        plc.get("electrode_count")
        if plc.get("electrode_count") is not None
        else payload.get("electrode_count")
    )

    normalized = {
        "event_id": str(event_id),
        "line_id": payload.get("line_id", LINE_ID),
        "station_code": station.code,
        "pallet_id": pallet_id,
        "pallet_run_id": pallet_run_id,
        "weld_id": weld_id,
        "source_type": payload.get("source_type", "simulator"),
        "source_timestamp": timestamp,
        "distancia": round(distancia, 3) if distancia is not None else None,
        "fuerza": round(fuerza, 2) if fuerza is not None else None,
        "ampers": round(ampers, 2) if ampers is not None else None,
        "volts": round(volts, 2) if volts is not None else None,
        "watts": round(watts, 2) if watts is not None else None,
        "real_station": str(real_station) if real_station is not None else None,
        "schedule": schedule,
        "plc_ip": plc.get("plc_ip") or payload.get("plc_ip"),
        "electrode_count": str(electrode_count) if electrode_count is not None else None,
        "voltaje": round(voltaje, 2),
        "corriente": round(corriente, 2) if corriente is not None else None,
        "presion": round(presion, 2),
        "tiempo_ms": round(tiempo_ms, 2) if tiempo_ms is not None else None,
        "ml_result": ml_result,
        "raw_payload": payload,
    }
    return evaluate_detection(normalized)


def evaluate_detection(event: dict[str, Any]) -> dict[str, Any]:
    ml_result = event.get("ml_result") or {}
    model_result = ml_result if "is_anomaly" in ml_result else predict(event)

    if model_result and "is_anomaly" in model_result:
        is_anomaly = bool(model_result.get("is_anomaly"))
        anomaly_score = float(model_result.get("score") or (0.98 if is_anomaly else 0.05))
        confidence = float(model_result.get("confidence") or anomaly_score)
        detection_source = model_result.get("source") or "ml_model"
        detection_reason = model_result.get("reason") or "Salida del modelo de deteccion"
    else:
        detection_source = "rule_fallback"
        anomaly_score, is_anomaly, detection_reason = evaluate_rule_fallback(event)
        confidence = max(0.95 if is_anomaly else 0.08, min(anomaly_score, 0.99))

    event["is_anomaly"] = is_anomaly
    event["status"] = "MALO" if is_anomaly else "BUENO"
    event["anomaly_score"] = round(min(max(anomaly_score, 0.0), 0.99), 4)
    event["confidence"] = round(min(max(confidence, 0.0), 0.99), 4)
    event["detection_source"] = detection_source
    event["detection_reason"] = detection_reason
    return event


PLC_RULE_FALLBACK_THRESHOLD = 0.5


def evaluate_rule_fallback(event: dict[str, Any]) -> tuple[float, bool, str]:
    reasons = []

    if event.get("ampers") is not None:
        amperage = float(event["ampers"])
        volts = float(event["volts"] or 0)
        # Anchor the rule on values that are clearly out of band for the historical
        # busbar dataset: amperage above ~13.5 or voltage below ~1.8 V. The temporary
        # rule must stay conservative until the real ML model lands; otherwise it
        # floods the alerts table and ruins dashboard latency.
        amperage_component = max((amperage - 13.5) / 1.5, 0)
        low_voltage_component = max((1.8 - volts) / 0.8, 0)
        anomaly_score = min(max(amperage_component, low_voltage_component), 0.99)
        is_anomaly = anomaly_score >= PLC_RULE_FALLBACK_THRESHOLD

        if is_anomaly and amperage > 13.5:
            reasons.append(f"Amperaje alto ({amperage:.2f})")
        if is_anomaly and volts < 1.8:
            reasons.append(f"Voltaje bajo ({volts:.2f} V)")
    else:
        voltage_component = max((event["voltaje"] - 12.5) / 1.5, 0)
        pressure_component = max((2.8 - event["presion"]) / 0.8, 0)
        anomaly_score = min(max(voltage_component, pressure_component), 0.99)
        is_anomaly = anomaly_score > 0

        if event["voltaje"] > 12.5:
            reasons.append(f"Voltaje alto ({event['voltaje']} V)")
        if event["presion"] < 2.8:
            reasons.append(f"Presion baja ({event['presion']} bar)")

    return anomaly_score, is_anomaly, " / ".join(reasons) if reasons else "Operacion nominal"


def persist_event(event: dict[str, Any]) -> bool:
    station = station_by_code(event["station_code"]) or station_for_weld_id(event["weld_id"])
    alert_id = f"alert-{event['event_id']}"
    inserted = False

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO weld_events (
                    event_id,
                    line_id,
                    station_code,
                    pallet_id,
                    pallet_run_id,
                    weld_id,
                    source_type,
                    source_timestamp,
                    distancia,
                    fuerza,
                    ampers,
                    volts,
                    watts,
                    real_station,
                    schedule,
                    plc_ip,
                    electrode_count,
                    voltaje,
                    corriente,
                    presion,
                    tiempo_ms,
                    status,
                    is_anomaly,
                    anomaly_score,
                    confidence,
                    detection_source,
                    detection_reason,
                    raw_payload
                )
                VALUES (
                    %(event_id)s,
                    %(line_id)s,
                    %(station_code)s,
                    %(pallet_id)s,
                    %(pallet_run_id)s,
                    %(weld_id)s,
                    %(source_type)s,
                    %(source_timestamp)s,
                    %(distancia)s,
                    %(fuerza)s,
                    %(ampers)s,
                    %(volts)s,
                    %(watts)s,
                    %(real_station)s,
                    %(schedule)s,
                    %(plc_ip)s,
                    %(electrode_count)s,
                    %(voltaje)s,
                    %(corriente)s,
                    %(presion)s,
                    %(tiempo_ms)s,
                    %(status)s,
                    %(is_anomaly)s,
                    %(anomaly_score)s,
                    %(confidence)s,
                    %(detection_source)s,
                    %(detection_reason)s,
                    %(raw_payload)s
                )
                ON CONFLICT (event_id) DO NOTHING
                RETURNING event_id
                """,
                {**event, "raw_payload": Json(event["raw_payload"])},
            )
            inserted = cur.fetchone() is not None

            if not inserted:
                conn.commit()
                return False

            if event["is_anomaly"]:
                cur.execute(
                    """
                    INSERT INTO alerts (
                        alert_id,
                        event_id,
                        line_id,
                        station_code,
                        pallet_id,
                        pallet_run_id,
                        weld_id,
                        title,
                        message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        alert_id,
                        event["event_id"],
                        event["line_id"],
                        event["station_code"],
                        event["pallet_id"],
                        event["pallet_run_id"],
                        event["weld_id"],
                        f"Anomalia detectada / {station.display_name}",
                        f"{event['detection_reason']}. Pallet {event['pallet_id']}, soldadura {event['weld_id']}/8.",
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE alerts
                    SET status = 'RESOLVED', resolved_at = NOW()
                    WHERE station_code = %s
                      AND status = 'ACTIVE'
                    """,
                    (event["station_code"],),
                )
        conn.commit()

    return inserted


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: serialize_value(value) for key, value in row.items()}


def fetch_dashboard_data() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    s.station_code,
                    s.display_name,
                    s.node_label,
                    s.station_order,
                    e.event_id,
                    e.pallet_id,
                    e.pallet_run_id,
                    e.weld_id,
                    e.status,
                    e.source_timestamp,
                    e.voltaje,
                    e.ampers,
                    e.volts,
                    e.real_station,
                    e.schedule,
                    e.anomaly_score,
                    e.confidence,
                    a.alert_id,
                    a.title AS alert_title,
                    a.message AS alert_message
                FROM stations s
                LEFT JOIN LATERAL (
                    SELECT *
                    FROM weld_events w
                    WHERE w.station_code = s.station_code
                    ORDER BY w.source_timestamp DESC
                    LIMIT 1
                ) e ON TRUE
                LEFT JOIN LATERAL (
                    SELECT alert_id, title, message
                    FROM alerts al
                    WHERE al.station_code = s.station_code
                      AND al.status = 'ACTIVE'
                    ORDER BY al.created_at DESC
                    LIMIT 1
                ) a ON TRUE
                WHERE s.line_id = %s
                ORDER BY s.station_order
                """,
                (LINE_ID,),
            )
            stations = [serialize_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    e.event_id,
                    e.pallet_id,
                    e.pallet_run_id,
                    e.weld_id,
                    e.status,
                    e.source_timestamp,
                    e.voltaje,
                    e.presion,
                    e.distancia,
                    e.fuerza,
                    e.ampers,
                    e.volts,
                    e.watts,
                    e.real_station,
                    e.schedule,
                    e.anomaly_score,
                    e.confidence,
                    e.detection_reason,
                    s.display_name AS station_name,
                    a.alert_id
                FROM weld_events e
                JOIN stations s ON s.station_code = e.station_code
                LEFT JOIN alerts a ON a.event_id = e.event_id
                WHERE e.line_id = %s
                ORDER BY e.source_timestamp DESC
                LIMIT 10
                """,
                (LINE_ID,),
            )
            recent_logs = [serialize_row(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_welds,
                    COUNT(*) FILTER (WHERE is_anomaly) AS anomaly_count,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE NOT is_anomaly) / NULLIF(COUNT(*), 0),
                        1
                    ) AS success_rate
                FROM weld_events
                WHERE line_id = %s
                  AND source_timestamp >= CURRENT_DATE::timestamptz
                  AND source_timestamp < (CURRENT_DATE + INTERVAL '1 day')::timestamptz
                """,
                (LINE_ID,),
            )
            stats = serialize_row(cur.fetchone() or {})

            cur.execute(
                """
                SELECT
                    TO_CHAR(date_trunc('hour', source_timestamp), 'HH24:00') AS bucket,
                    COUNT(*) AS welds
                FROM weld_events
                WHERE line_id = %s
                  AND source_timestamp >= NOW() - INTERVAL '8 hours'
                GROUP BY 1
                ORDER BY 1
                """,
                (LINE_ID,),
            )
            throughput_rows = cur.fetchall()

            cur.execute(
                """
                SELECT alert_id, title, message
                FROM alerts
                WHERE line_id = %s
                  AND status = 'ACTIVE'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (LINE_ID,),
            )
            active_alert = cur.fetchone()

    throughput_map = {row["bucket"]: int(row["welds"]) for row in throughput_rows}
    buckets = []
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for offset in range(7, -1, -1):
        hour = now - timedelta(hours=offset)
        label = hour.strftime("%H:00")
        buckets.append({"bucket": label, "welds": throughput_map.get(label, 0)})

    return {
        "metadata": {
            "line_label": LINE_LABEL,
            "operator_name": OPERATOR_NAME,
            "operator_line_label": OPERATOR_LINE_LABEL,
        },
        "stations": stations,
        "recent_logs": recent_logs,
        "stats": {
            "total_welds": int(stats.get("total_welds") or 0),
            "anomaly_count": int(stats.get("anomaly_count") or 0),
            "success_rate": float(stats.get("success_rate") or 0),
            "throughput": buckets,
        },
        "active_alert": serialize_row(active_alert) if active_alert else None,
    }


def fetch_history_data(
    station_code: str | None,
    status: str | None,
    pallet_id: str | None,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    clauses = ["e.line_id = %s"]
    params: list[Any] = [LINE_ID]

    if station_code:
        clauses.append("e.station_code = %s")
        params.append(station_code)
    if status:
        clauses.append("e.status = %s")
        params.append(status)
    if pallet_id:
        clauses.append("e.pallet_id ILIKE %s")
        params.append(f"%{pallet_id}%")
    if date_from:
        clauses.append("e.source_timestamp >= %s::date")
        params.append(date_from)
    if date_to:
        clauses.append("e.source_timestamp < (%s::date + INTERVAL '1 day')")
        params.append(date_to)

    where_sql = " AND ".join(clauses)
    offset = max(page - 1, 0) * page_size

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_records,
                    COUNT(*) FILTER (WHERE e.is_anomaly) AS anomaly_count,
                    ROUND(
                        100.0 * COUNT(*) FILTER (WHERE NOT e.is_anomaly) / NULLIF(COUNT(*), 0),
                        1
                    ) AS success_rate
                FROM (
                    SELECT e.is_anomaly
                    FROM weld_events e
                    WHERE {where_sql}
                    LIMIT %s
                ) e
                """,
                [*params, HISTORY_COUNT_CAP + 1],
            )
            summary = serialize_row(cur.fetchone() or {})

            cur.execute(
                f"""
                SELECT
                    e.event_id,
                    e.pallet_id,
                    e.pallet_run_id,
                    e.weld_id,
                    e.source_timestamp,
                    e.voltaje,
                    e.presion,
                    e.distancia,
                    e.fuerza,
                    e.ampers,
                    e.volts,
                    e.watts,
                    e.real_station,
                    e.schedule,
                    e.status,
                    s.display_name AS station_name,
                    a.alert_id
                FROM weld_events e
                JOIN stations s ON s.station_code = e.station_code
                LEFT JOIN alerts a ON a.event_id = e.event_id
                WHERE {where_sql}
                ORDER BY e.source_timestamp DESC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, offset],
            )
            items = [serialize_row(row) for row in cur.fetchall()]

    raw_count = int(summary.get("total_records") or 0)
    count_capped = raw_count > HISTORY_COUNT_CAP
    total_records = HISTORY_COUNT_CAP if count_capped else raw_count
    total_pages = max((total_records + page_size - 1) // page_size, 1)

    return {
        "metadata": {
            "line_label": LINE_LABEL,
            "operator_name": OPERATOR_NAME,
            "operator_line_label": OPERATOR_LINE_LABEL,
        },
        "items": items,
        "page": page,
        "page_size": page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "count_capped": count_capped,
        "station_options": [
            {"station_code": station.code, "display_name": station.display_name}
            for station in STATIONS
        ],
        "summary": {
            "total_analyzed": total_records,
            "success_rate": float(summary.get("success_rate") or 0),
            "errors": int(summary.get("anomaly_count") or 0),
            "active_line": LINE_LABEL.upper(),
            "count_capped": count_capped,
        },
    }


def fetch_alert_detail(alert_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    a.alert_id,
                    a.title,
                    a.message,
                    a.status AS alert_status,
                    a.created_at,
                    e.event_id,
                    e.pallet_id,
                    e.pallet_run_id,
                    e.weld_id,
                    e.source_timestamp,
                    e.distancia,
                    e.fuerza,
                    e.ampers,
                    e.volts,
                    e.watts,
                    e.real_station,
                    e.schedule,
                    e.plc_ip,
                    e.electrode_count,
                    e.voltaje,
                    e.corriente,
                    e.presion,
                    e.tiempo_ms,
                    e.anomaly_score,
                    e.confidence,
                    e.detection_source,
                    e.detection_reason,
                    s.display_name AS station_name,
                    s.node_label
                FROM alerts a
                JOIN weld_events e ON e.event_id = a.event_id
                JOIN stations s ON s.station_code = a.station_code
                WHERE a.alert_id = %s
                """,
                (alert_id,),
            )
            alert = cur.fetchone()
            if not alert:
                return None

            timeline_where = "e.pallet_run_id = %s" if alert.get("pallet_run_id") else "e.pallet_id = %s"
            timeline_param = alert.get("pallet_run_id") or alert["pallet_id"]
            cur.execute(
                f"""
                SELECT
                    e.event_id,
                    e.pallet_run_id,
                    e.weld_id,
                    e.source_timestamp,
                    e.distancia,
                    e.fuerza,
                    e.ampers,
                    e.volts,
                    e.watts,
                    e.real_station,
                    e.schedule,
                    e.voltaje,
                    e.corriente,
                    e.presion,
                    e.tiempo_ms,
                    e.anomaly_score,
                    e.confidence,
                    e.status,
                    e.is_anomaly,
                    a.alert_id
                FROM weld_events e
                LEFT JOIN alerts a ON a.event_id = e.event_id
                WHERE {timeline_where}
                ORDER BY e.weld_id ASC, e.source_timestamp ASC
                """,
                (timeline_param,),
            )
            pallet_events = [serialize_row(row) for row in cur.fetchall()]

    serialized_alert = serialize_row(alert)
    serialized_alert["timeline_label"] = f"Pallet {serialized_alert['pallet_id']}"

    return {
        "metadata": {
            "line_label": LINE_LABEL,
            "operator_name": OPERATOR_NAME,
            "operator_line_label": OPERATOR_LINE_LABEL,
        },
        "alert": serialized_alert,
        "timeline": pallet_events,
    }
