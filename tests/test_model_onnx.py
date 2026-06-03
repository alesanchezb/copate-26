from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BRAIN = ROOT / "brain"
sys.path.insert(0, str(BRAIN))

import model  # noqa: E402


class CapturingSession:
    def __init__(self, offset: float = 0.0) -> None:
        self.offset = offset
        self.inputs = []

    def run(self, output_names, feed):
        x_scaled = feed["input"]
        self.inputs.append(x_scaled.copy())
        return x_scaled + self.offset, None


class CleaNetModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = CapturingSession()
        model._sessions = {
            "150_Sch1": {
                "sess": self.session,
                "meta": {
                    "scaler": {
                        "mean": [0, 0, 0, 0, 0],
                        "scale": [1, 1, 1, 1, 1],
                    },
                    "thresholds": {
                        "p90": 0.1,
                        "p95": 0.2,
                        "p99": 0.3,
                    },
                },
            },
            "155_Sch2": {
                "sess": CapturingSession(),
                "meta": {
                    "scaler": {
                        "mean": [0, 0, 0, 0, 0],
                        "scale": [1, 1, 1, 1, 1],
                    },
                    "thresholds": {
                        "p90": 0.1,
                        "p95": 0.2,
                        "p99": 0.3,
                    },
                },
            },
        }
        model._clamps = {
            "distancia_delta": {"low": -0.1, "high": 0.1},
            "fuerza_delta": {"low": -3.0, "high": 3.0},
            "watts_delta": {"low": -0.5, "high": 0.5},
        }
        model._last_weld_by_group.clear()

    def test_first_weld_uses_zero_deltas_and_second_weld_clamps(self) -> None:
        first = {
            "real_station": "150",
            "schedule": "Sch1",
            "distancia": 0.30,
            "fuerza": 10,
            "ampers": 12,
            "volts": 2,
            "watts": 9.0,
        }
        second = {
            **first,
            "distancia": 0.60,
            "fuerza": 20,
            "watts": 11.0,
        }

        model.predict(first)
        model.predict(second)

        first_input = self.session.inputs[0][0].tolist()
        second_input = self.session.inputs[1][0].tolist()
        for actual, expected in zip(first_input, [0.30, 9.0, 0.0, 0.0, 0.0]):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(second_input, [0.60, 11.0, 0.1, 3.0, 0.5]):
            self.assertAlmostEqual(actual, expected)

    def test_exact_model_selection_and_missing_model_returns_none(self) -> None:
        exact = model.predict(
            {
                "real_station": "155",
                "schedule": "Sch2",
                "distancia": 0.4,
                "fuerza": 10,
                "ampers": 12,
                "volts": 2,
                "watts": 9,
            }
        )
        missing = model.predict(
            {
                "real_station": "140",
                "schedule": "Sch1",
                "distancia": 0.4,
                "fuerza": 10,
                "ampers": 12,
                "volts": 2,
                "watts": 9,
            }
        )

        self.assertEqual(exact["model_key"], "155_Sch2")
        self.assertFalse(exact["model_is_fallback"])
        self.assertIsNone(missing)

    def test_level_thresholds_drive_anomaly_flag(self) -> None:
        self.session.offset = math.sqrt(0.25)
        possible_bad = model.predict(
            {
                "real_station": "150",
                "schedule": "Sch1",
                "distancia": 0.4,
                "fuerza": 10,
                "ampers": 12,
                "volts": 2,
                "watts": 9,
            }
        )

        self.assertEqual(possible_bad["model_level"], "POSIBLE_MALA")
        self.assertTrue(possible_bad["is_anomaly"])


if __name__ == "__main__":
    unittest.main()
