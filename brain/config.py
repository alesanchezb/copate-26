from dataclasses import dataclass
from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

APP_NAME = "WeldGuard AI"
LINE_ID = os.environ.get("LINE_ID", "linea1")
LINE_LABEL = os.environ.get("LINE_LABEL", "Control de linea 1")
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "Operador 01")
OPERATOR_LINE_LABEL = os.environ.get("OPERATOR_LINE_LABEL", "Linea de soldadura alfa")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC = os.environ.get("MQTT_TOPIC", "fabrica/linea1/soldadura")

API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))

DB_CONFIG = {
    "host": os.environ.get("POSTGRES_HOST", "db"),
    "database": os.environ.get("POSTGRES_DB", "soldadura_db"),
    "user": os.environ.get("POSTGRES_USER", "admin"),
    "password": os.environ.get("POSTGRES_PASSWORD", "industrial_pass"),
}


@dataclass(frozen=True)
class StationConfig:
    code: str
    node_label: str
    display_name: str
    station_order: int
    weld_start: int
    weld_end: int


STATIONS = (
    StationConfig("station_1", "NODE 01", "Estacion 1", 1, 1, 2),
    StationConfig("station_2", "NODE 02", "Estacion 2", 2, 3, 4),
    StationConfig("station_3", "NODE 03", "Estacion 3", 3, 5, 6),
    StationConfig("station_4", "NODE 04", "Estacion 4", 4, 7, 8),
)

REAL_STATION_TO_CODE = {
    "140": "station_1",
    "145": "station_2",
    "150": "station_3",
    "155": "station_4",
}

SCHEDULE_TO_ORDER = {
    "Sch1": 1,
    "Sch2": 2,
}


def station_for_weld_id(weld_id: int) -> StationConfig:
    for station in STATIONS:
        if station.weld_start <= weld_id <= station.weld_end:
            return station
    return STATIONS[-1]


def station_by_code(station_code: str) -> StationConfig | None:
    if not station_code:
        return None

    normalized = str(station_code).strip().lower()
    for station in STATIONS:
        if normalized in {
            station.code.lower(),
            station.display_name.lower(),
            station.node_label.lower(),
        }:
            return station
    return None


def normalize_schedule(schedule: str | int | None) -> str | None:
    if schedule is None:
        return None
    raw = str(schedule).strip()
    if not raw:
        return None
    if raw.lower().startswith("sch"):
        suffix = raw[3:]
    else:
        suffix = raw
    try:
        normalized = f"Sch{int(suffix)}"
    except ValueError:
        return raw
    return normalized if normalized in SCHEDULE_TO_ORDER else raw


def station_by_real_station(real_station: str | int | None) -> StationConfig | None:
    if real_station is None:
        return None
    station_code = REAL_STATION_TO_CODE.get(str(real_station).strip())
    return station_by_code(station_code or "")


def weld_id_for_real_station(real_station: str | int | None, schedule: str | int | None) -> int | None:
    station = station_by_real_station(real_station)
    schedule_name = normalize_schedule(schedule)
    if not station or schedule_name not in SCHEDULE_TO_ORDER:
        return None
    return (station.station_order - 1) * 2 + SCHEDULE_TO_ORDER[schedule_name]
