from __future__ import annotations

import sqlite3
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from plc_gateway.adapter import PlcMqttAdapter
from plc_gateway.clients import SimulatedTagClient
from plc_gateway.mapping import weld_id_for
from plc_gateway.simulation import HistoricalPlcProducer
from plc_gateway.sources import HERMOSILLO_TZ, HistoricalWeldDataSource, WeldSample


class CapturingPublisher:
    def __init__(self) -> None:
        self.items = []

    def publish(self, topic, payload) -> None:
        self.items.append((topic, payload))


class PlcGatewayTests(unittest.TestCase):
    def test_station_schedule_mapping_to_weld_id(self) -> None:
        self.assertEqual(weld_id_for("140", "Sch1"), 1)
        self.assertEqual(weld_id_for("145", "Sch2"), 4)
        self.assertEqual(weld_id_for("150", "Sch1"), 5)
        self.assertEqual(weld_id_for("155", "Sch2"), 8)

    def test_sqlite_source_loads_contiguous_window(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "WeldParameters.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE Parameters (
                        id INTEGER PRIMARY KEY,
                        timestamp TEXT,
                        distancia REAL,
                        fuerza REAL,
                        ampers REAL,
                        volts REAL,
                        watts REAL,
                        estacion TEXT,
                        sch TEXT,
                        plc_ip TEXT,
                        PalletId INTEGER,
                        Electrodecount TEXT
                    )
                    """
                )
                for idx, station in enumerate(("140", "145", "150", "155"), 1):
                    conn.execute(
                        """
                        INSERT INTO Parameters
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            idx,
                            f"2026-02-10 00:00:0{idx}",
                            0.4,
                            90 + idx,
                            10 + idx / 10,
                            2.5,
                            7.0,
                            station,
                            "Sch1",
                            "172.16.14.1",
                            13,
                            str(600 + idx),
                        ),
                    )

            source = HistoricalWeldDataSource(db_path=db_path, csv_path=Path(temp_dir) / "missing.csv")
            rows = source.load_window(2)
            backend = source.backend

        self.assertEqual(len(rows), 2)
        self.assertTrue(all(isinstance(row, WeldSample) for row in rows))
        self.assertEqual(backend, "sqlite")

    def test_simulated_handshake_publishes_once_and_clears_flag(self) -> None:
        client = SimulatedTagClient()
        publisher = CapturingPublisher()
        adapter = PlcMqttAdapter(
            tag_client=client,
            publisher=publisher,
            topic="fabrica/linea1/soldadura",
            handshake_pulse_seconds=0,
            timestamp_mode="historical",
        )
        producer = HistoricalPlcProducer(
            source=None,
            tag_client=client,
            handshake_timeout_seconds=2,
        )
        sample = WeldSample(
            raw_id="86539",
            timestamp=datetime(2026, 2, 10, 0, 0, 2, tzinfo=HERMOSILLO_TZ),
            distancia=0.482,
            fuerza=93,
            ampers=10.62,
            volts=2.6,
            watts=7.26,
            real_station="140",
            schedule="Sch1",
            plc_ip="172.16.14.1",
            pallet_id="13",
            electrode_count="652",
        )

        result = {}

        def emit() -> None:
            result["ack"] = producer.emit_sample(sample)

        thread = threading.Thread(target=emit)
        thread.start()
        deadline = time.time() + 2
        while time.time() < deadline and not publisher.items:
            adapter.poll_once()
            time.sleep(0.01)
        thread.join(timeout=2)

        self.assertTrue(result["ack"])
        self.assertEqual(len(publisher.items), 1)
        topic, payload = publisher.items[0]
        self.assertEqual(topic, "fabrica/linea1/soldadura")
        self.assertEqual(payload["station_id"], "station_1")
        self.assertEqual(payload["weld_id"], 1)
        self.assertEqual(payload["pallet_id"], "13")
        self.assertEqual(payload["plc"]["raw_id"], "86539")
        self.assertEqual(payload["params"]["ampers"], 10.62)

        adapter.poll_once()
        self.assertEqual(len(publisher.items), 1)


if __name__ == "__main__":
    unittest.main()
