from __future__ import annotations

import csv
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .mapping import station_for_real_station, weld_id_for, normalize_schedule


HERMOSILLO_TZ = ZoneInfo("America/Hermosillo")


@dataclass(frozen=True)
class WeldSample:
    raw_id: str
    timestamp: datetime
    distancia: float
    fuerza: float
    ampers: float
    volts: float
    watts: float
    real_station: str
    schedule: str
    plc_ip: str
    pallet_id: str
    electrode_count: str

    @property
    def station_id(self) -> str:
        return station_for_real_station(self.real_station).station_id

    @property
    def weld_id(self) -> int:
        return weld_id_for(self.real_station, self.schedule)


def parse_plc_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=HERMOSILLO_TZ)
    return parsed.astimezone(HERMOSILLO_TZ)


def sample_from_mapping(row: dict[str, Any]) -> WeldSample:
    real_station = str(row["estacion"]).strip()
    station_for_real_station(real_station)
    schedule = normalize_schedule(row["sch"])

    return WeldSample(
        raw_id=str(row["id"]),
        timestamp=parse_plc_timestamp(row["timestamp"]),
        distancia=float(row["distancia"]),
        fuerza=float(row["fuerza"]),
        ampers=float(row["ampers"]),
        volts=float(row["volts"]),
        watts=float(row["watts"]),
        real_station=real_station,
        schedule=schedule,
        plc_ip=str(row["plc_ip"]).strip(),
        pallet_id=str(row["PalletId"]).strip(),
        electrode_count=str(row["Electrodecount"]).strip(),
    )


class HistoricalWeldDataSource:
    """Loads contiguous historical PLC rows from SQLite first, then CSV fallback."""

    def __init__(
        self,
        db_path: str | Path = "plc_reader_y_app/WeldParameters.db",
        csv_path: str | Path = "plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv",
        rng: random.Random | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.csv_path = Path(csv_path)
        self.rng = rng or random.Random()
        self._csv_cache: list[dict[str, Any]] | None = None

    @property
    def backend(self) -> str:
        if self.db_path.exists():
            return "sqlite"
        if self.csv_path.exists():
            return "csv"
        raise FileNotFoundError(
            f"No existe fuente historica SQLite ({self.db_path}) ni CSV ({self.csv_path})."
        )

    def load_window(self, window_size: int = 256) -> list[WeldSample]:
        if window_size <= 0:
            raise ValueError("window_size debe ser mayor a cero")
        if self.backend == "sqlite":
            return self._load_sqlite_window(window_size)
        return self._load_csv_window(window_size)

    def iter_windows(self, window_size: int = 256) -> Iterable[list[WeldSample]]:
        while True:
            yield self.load_window(window_size)

    def _load_sqlite_window(self, window_size: int) -> list[WeldSample]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            min_id, max_id = cur.execute(
                "SELECT MIN(id), MAX(id) FROM Parameters"
            ).fetchone()
            if min_id is None or max_id is None:
                return []

            start_id = self.rng.randint(int(min_id), int(max_id))
            rows = cur.execute(
                """
                SELECT id, timestamp, distancia, fuerza, ampers, volts, watts,
                       estacion, sch, plc_ip, PalletId, Electrodecount
                FROM Parameters
                WHERE id >= ?
                ORDER BY id
                LIMIT ?
                """,
                (start_id, window_size),
            ).fetchall()

            if len(rows) < window_size:
                rows.extend(
                    cur.execute(
                        """
                        SELECT id, timestamp, distancia, fuerza, ampers, volts, watts,
                               estacion, sch, plc_ip, PalletId, Electrodecount
                        FROM Parameters
                        ORDER BY id
                        LIMIT ?
                        """,
                        (window_size - len(rows),),
                    ).fetchall()
                )

        return [sample_from_mapping(dict(row)) for row in rows]

    def _load_csv_window(self, window_size: int) -> list[WeldSample]:
        if self._csv_cache is None:
            with self.csv_path.open(newline="", encoding="utf-8") as file:
                self._csv_cache = list(csv.DictReader(file))

        if not self._csv_cache:
            return []

        max_start = max(len(self._csv_cache) - window_size, 0)
        start = self.rng.randint(0, max_start)
        rows = self._csv_cache[start : start + window_size]
        return [sample_from_mapping(row) for row in rows]
