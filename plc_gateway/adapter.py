from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Protocol

from .clients import TagClient
from .mapping import (
    SCHEDULE_ORDER,
    STATION_MAPPINGS,
    flag_tag,
    handshake_tag,
    value_tags,
    weld_id_for,
)
from .run_tracker import PalletRunTracker
from .sources import HERMOSILLO_TZ


class JsonPublisher(Protocol):
    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        ...


class PahoMqttPublisher:
    def __init__(self, broker: str, port: int, keepalive: int = 60) -> None:
        import paho.mqtt.client as mqtt

        self._client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self._client.connect(broker, port, keepalive)
        self._client.loop_start()

    def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._client.publish(topic, json.dumps(payload, ensure_ascii=False))

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


class PlcMqttAdapter:
    def __init__(
        self,
        tag_client: TagClient,
        publisher: JsonPublisher,
        topic: str,
        line_id: str = "linea1",
        source_type: str = "plc_simulator",
        poll_interval_seconds: float = 0.1,
        handshake_pulse_seconds: float = 0.25,
        run_tracker: PalletRunTracker | None = None,
        timestamp_mode: str = "now",
    ) -> None:
        if timestamp_mode not in {"now", "historical"}:
            raise ValueError("timestamp_mode debe ser 'now' o 'historical'")

        self.tag_client = tag_client
        self.publisher = publisher
        self.topic = topic
        self.line_id = line_id
        self.source_type = source_type
        self.poll_interval_seconds = poll_interval_seconds
        self.handshake_pulse_seconds = handshake_pulse_seconds
        self.run_tracker = run_tracker or PalletRunTracker()
        self.timestamp_mode = timestamp_mode
        self._processed_flags: set[tuple[str, str]] = set()

    def run_forever(self) -> None:
        while True:
            self.poll_once()
            time.sleep(self.poll_interval_seconds)

    def poll_once(self) -> list[dict[str, Any]]:
        published: list[dict[str, Any]] = []

        for station in STATION_MAPPINGS:
            for schedule in SCHEDULE_ORDER:
                flag = flag_tag(schedule, station.plc_station_index)
                flag_key = (station.plc_ip, flag)
                flag_value = self.tag_client.read(station.plc_ip, flag).Value

                if flag_value != 1:
                    self._processed_flags.discard(flag_key)
                    continue

                if flag_key in self._processed_flags:
                    continue

                payload = self._build_payload(station, schedule, flag)
                self.publisher.publish(self.topic, payload)
                self._pulse_handshake(station.plc_ip, schedule, station.plc_station_index)
                self._processed_flags.add(flag_key)
                published.append(payload)

        return published

    def _build_payload(self, station, schedule: str, flag: str) -> dict[str, Any]:
        tags = value_tags(schedule, station.plc_station_index)
        values = {
            name: self.tag_client.read(station.plc_ip, tag).Value
            for name, tag in tags.items()
        }
        self._validate_values(values)

        metadata = self._metadata(station.plc_ip, flag)
        event_timestamp = self._event_timestamp(metadata)
        pallet_id = str(values["pallet_id"])
        pallet_run_id = self.run_tracker.assign(
            pallet_id=pallet_id,
            real_station=station.real_station,
            schedule=schedule,
            observed_at=event_timestamp,
        )

        return {
            "event_id": f"plc-{uuid.uuid4()}",
            "line_id": self.line_id,
            "source_type": self.source_type,
            "timestamp": event_timestamp.isoformat(),
            "station_id": station.station_id,
            "weld_id": weld_id_for(station.real_station, schedule),
            "pallet_id": pallet_id,
            "pallet_run_id": pallet_run_id,
            "params": {
                "distancia": round(float(values["distancia"]), 3),
                "fuerza": round(float(values["fuerza"]), 2),
                "ampers": round(float(values["ampers"]), 2),
                "volts": round(float(values["volts"]), 2),
                "watts": round(float(values["watts"]), 2),
            },
            "plc": {
                "real_station": station.real_station,
                "schedule": schedule,
                "plc_ip": station.plc_ip,
                "electrode_count": str(values["electrode_count"]),
                "raw_id": metadata.get("raw_id"),
                "raw_timestamp": metadata.get("raw_timestamp"),
            },
        }

    def _event_timestamp(self, metadata: dict[str, Any]) -> datetime:
        if self.timestamp_mode == "historical" and metadata.get("source_timestamp"):
            return metadata["source_timestamp"]
        return datetime.now(HERMOSILLO_TZ)

    def _metadata(self, plc_ip: str, flag: str) -> dict[str, Any]:
        getter = getattr(self.tag_client, "get_metadata", None)
        if not callable(getter):
            return {}
        return getter(plc_ip, flag)

    def _pulse_handshake(self, plc_ip: str, schedule: str, plc_station_index: int) -> None:
        tag = handshake_tag(schedule, plc_station_index)
        self.tag_client.write(plc_ip, tag, 1)
        time.sleep(self.handshake_pulse_seconds)
        self.tag_client.write(plc_ip, tag, 0)

    def _validate_values(self, values: dict[str, Any]) -> None:
        for key in ("distancia", "fuerza", "ampers", "volts", "watts"):
            if values[key] is None:
                raise ValueError(f"Tag PLC sin valor numerico: {key}")
            float(values[key])
