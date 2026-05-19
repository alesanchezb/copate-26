from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StationMapping:
    real_station: str
    station_id: str
    station_order: int
    plc_ip: str
    plc_station_index: int


SCHEDULE_ORDER = {
    "Sch1": 1,
    "Sch2": 2,
}

STATION_MAPPINGS = (
    StationMapping("140", "station_1", 1, "172.16.14.1", 1),
    StationMapping("145", "station_2", 2, "172.16.14.1", 2),
    StationMapping("150", "station_3", 3, "172.16.15.1", 1),
    StationMapping("155", "station_4", 4, "172.16.15.1", 2),
)

STATION_BY_REAL = {station.real_station: station for station in STATION_MAPPINGS}
STATION_BY_CODE = {station.station_id: station for station in STATION_MAPPINGS}
STATION_BY_PLC_SLOT = {
    (station.plc_ip, station.plc_station_index): station
    for station in STATION_MAPPINGS
}


def normalize_real_station(value: object) -> str:
    return str(value).strip()


def normalize_schedule(value: object) -> str:
    raw = str(value).strip()
    if not raw:
        raise ValueError("Schedule vacio")
    if raw.lower().startswith("sch"):
        suffix = raw[3:]
    else:
        suffix = raw
    normalized = f"Sch{int(suffix)}"
    if normalized not in SCHEDULE_ORDER:
        raise ValueError(f"Schedule no soportado: {value!r}")
    return normalized


def station_for_real_station(value: object) -> StationMapping:
    real_station = normalize_real_station(value)
    try:
        return STATION_BY_REAL[real_station]
    except KeyError as exc:
        raise ValueError(f"Estacion real no soportada: {value!r}") from exc


def station_for_plc_slot(plc_ip: str, plc_station_index: int) -> StationMapping:
    try:
        return STATION_BY_PLC_SLOT[(str(plc_ip), int(plc_station_index))]
    except KeyError as exc:
        raise ValueError(
            f"Slot PLC no soportado: plc_ip={plc_ip!r}, station={plc_station_index!r}"
        ) from exc


def weld_id_for(real_station: object, schedule: object) -> int:
    station = station_for_real_station(real_station)
    schedule_name = normalize_schedule(schedule)
    return (station.station_order - 1) * 2 + SCHEDULE_ORDER[schedule_name]


def flag_tag(schedule: object, plc_station_index: int) -> str:
    schedule_name = normalize_schedule(schedule)
    return f"NewData{schedule_name}St{int(plc_station_index)}"


def handshake_tag(schedule: object, plc_station_index: int) -> str:
    schedule_name = normalize_schedule(schedule)
    return f"NewData{schedule_name}St{int(plc_station_index)}HndShk"


def value_tags(schedule: object, plc_station_index: int) -> dict[str, str]:
    schedule_name = normalize_schedule(schedule)
    station_suffix = f"{schedule_name}St{int(plc_station_index)}"
    return {
        "fuerza": f"ForceLast{station_suffix}",
        "distancia": f"DistLast{station_suffix}",
        "ampers": f"AmpsLast{station_suffix}",
        "volts": f"VoltsLast{station_suffix}",
        "watts": f"WattsLast{station_suffix}",
        "electrode_count": f"ElctCtr{station_suffix}",
        "pallet_id": f"PalletId{station_suffix}",
    }
