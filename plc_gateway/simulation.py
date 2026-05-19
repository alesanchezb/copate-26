from __future__ import annotations

import logging
import time
from datetime import datetime

from .clients import SimulatedTagClient
from .mapping import flag_tag, handshake_tag, station_for_real_station, value_tags
from .sources import HistoricalWeldDataSource, WeldSample


class HistoricalPlcProducer:
    """Feeds historical weld rows into a simulated PLC tag table."""

    def __init__(
        self,
        source: HistoricalWeldDataSource,
        tag_client: SimulatedTagClient,
        window_size: int = 256,
        speed: float = 4.0,
        min_delay_seconds: float = 0.05,
        max_delay_seconds: float = 1.5,
        handshake_timeout_seconds: float = 5.0,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed debe ser mayor a cero")
        self.source = source
        self.tag_client = tag_client
        self.window_size = window_size
        self.speed = speed
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.handshake_timeout_seconds = handshake_timeout_seconds

    def run_forever(self, limit: int | None = None) -> None:
        emitted = 0
        previous_timestamp: datetime | None = None

        for window in self.source.iter_windows(self.window_size):
            for sample in window:
                self._sleep_for_rhythm(previous_timestamp, sample.timestamp)
                previous_timestamp = sample.timestamp

                self.emit_sample(sample)
                emitted += 1
                if limit is not None and emitted >= limit:
                    return

    def emit_sample(self, sample: WeldSample) -> bool:
        station = station_for_real_station(sample.real_station)
        tags = value_tags(sample.schedule, station.plc_station_index)
        flag = flag_tag(sample.schedule, station.plc_station_index)
        handshake = handshake_tag(sample.schedule, station.plc_station_index)

        self.tag_client.write_many(
            station.plc_ip,
            {
                tags["fuerza"]: sample.fuerza,
                tags["distancia"]: sample.distancia,
                tags["ampers"]: sample.ampers,
                tags["volts"]: sample.volts,
                tags["watts"]: sample.watts,
                tags["electrode_count"]: sample.electrode_count,
                tags["pallet_id"]: sample.pallet_id,
                handshake: 0,
            },
        )
        self.tag_client.set_metadata(
            station.plc_ip,
            flag,
            {
                "raw_id": sample.raw_id,
                "raw_timestamp": sample.timestamp.isoformat(),
                "source_timestamp": sample.timestamp,
            },
        )
        self.tag_client.write(station.plc_ip, flag, 1)

        # Real PLC pattern: NewData stays high until the consumer raises the handshake
        # AND lowers it again. Waiting for the full 1 -> 0 pulse keeps the simulator from
        # racing the adapter and dropping samples on back-to-back hits to the same slot.
        acknowledged = self.tag_client.wait_for_value(
            station.plc_ip,
            handshake,
            1,
            timeout_seconds=self.handshake_timeout_seconds,
        )
        if acknowledged:
            self.tag_client.wait_for_value(
                station.plc_ip,
                handshake,
                0,
                timeout_seconds=self.handshake_timeout_seconds,
            )

        self.tag_client.write(station.plc_ip, flag, 0)
        self.tag_client.clear_metadata(station.plc_ip, flag)

        if not acknowledged:
            logging.warning(
                "Timeout esperando handshake PLC simulado para %s %s pallet=%s raw_id=%s",
                sample.real_station,
                sample.schedule,
                sample.pallet_id,
                sample.raw_id,
            )

        return acknowledged

    def _sleep_for_rhythm(
        self,
        previous_timestamp: datetime | None,
        current_timestamp: datetime,
    ) -> None:
        if previous_timestamp is None:
            return
        raw_delay = max((current_timestamp - previous_timestamp).total_seconds(), 0)
        delay = raw_delay / self.speed
        delay = min(max(delay, self.min_delay_seconds), self.max_delay_seconds)
        time.sleep(delay)
