from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "brain"
sys.path.insert(0, str(BRAIN))

psycopg2_stub = types.ModuleType("psycopg2")
psycopg2_stub.connect = lambda **kwargs: None
extras_stub = types.ModuleType("psycopg2.extras")
extras_stub.Json = lambda value: value
extras_stub.RealDictCursor = object
sys.modules.setdefault("psycopg2", psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", extras_stub)

from repository import normalize_payload  # noqa: E402


class BrainNormalizationTests(unittest.TestCase):
    def test_legacy_payload_still_normalizes(self) -> None:
        event = normalize_payload(
            {
                "event_id": "legacy-1",
                "line_id": "linea1",
                "station_id": "station_1",
                "source_type": "simulator",
                "pallet_id": "PALLET_1",
                "weld_id": 1,
                "timestamp": "2026-05-12T12:00:00Z",
                "params": {
                    "voltaje": 12.8,
                    "corriente": 450,
                    "presion": 3.0,
                    "tiempo_ms": 800,
                },
            }
        )

        self.assertEqual(event["station_code"], "station_1")
        self.assertEqual(event["pallet_run_id"], "PALLET_1")
        self.assertEqual(event["status"], "MALO")
        self.assertEqual(event["detection_source"], "rule_fallback")

    def test_plc_payload_uses_canonical_fields_and_run_id(self) -> None:
        event = normalize_payload(
            {
                "event_id": "plc-1",
                "line_id": "linea1",
                "source_type": "plc_simulator",
                "timestamp": "2026-02-10T00:00:02-07:00",
                "station_id": "station_1",
                "weld_id": 1,
                "pallet_id": "13",
                "pallet_run_id": "13-20260210T000002-0001",
                "params": {
                    "distancia": 0.482,
                    "fuerza": 93,
                    "ampers": 10.62,
                    "volts": 2.6,
                    "watts": 7.26,
                },
                "plc": {
                    "real_station": "140",
                    "schedule": "Sch1",
                    "plc_ip": "172.16.14.1",
                    "electrode_count": "652",
                    "raw_id": 86539,
                },
            }
        )

        self.assertEqual(event["station_code"], "station_1")
        self.assertEqual(event["weld_id"], 1)
        self.assertEqual(event["pallet_id"], "13")
        self.assertEqual(event["pallet_run_id"], "13-20260210T000002-0001")
        self.assertEqual(event["real_station"], "140")
        self.assertEqual(event["schedule"], "Sch1")
        self.assertEqual(event["ampers"], 10.62)
        self.assertEqual(event["volts"], 2.6)
        self.assertEqual(event["status"], "BUENO")

    def test_plc_payload_can_derive_station_and_weld_from_real_station(self) -> None:
        event = normalize_payload(
            {
                "event_id": "plc-2",
                "timestamp": "2026-02-10T00:00:02-07:00",
                "source_type": "plc_simulator",
                "pallet_id": "-1",
                "pallet_run_id": "-1-run",
                "params": {
                    "distancia": 0.4,
                    "fuerza": 123,
                    "ampers": 15.0,
                    "volts": 1.4,
                    "watts": 10.0,
                },
                "plc": {
                    "real_station": "155",
                    "schedule": "Sch2",
                    "plc_ip": "172.16.15.1",
                    "electrode_count": "770",
                },
            }
        )

        self.assertEqual(event["station_code"], "station_4")
        self.assertEqual(event["weld_id"], 8)
        self.assertEqual(event["pallet_id"], "-1")
        self.assertEqual(event["status"], "MALO")


if __name__ == "__main__":
    unittest.main()
