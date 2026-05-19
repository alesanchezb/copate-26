from __future__ import annotations

import argparse
import logging
from pathlib import Path
from threading import Thread

from plc_gateway.adapter import PahoMqttPublisher, PlcMqttAdapter
from plc_gateway.clients import SimulatedTagClient
from plc_gateway.simulation import HistoricalPlcProducer
from plc_gateway.sources import HistoricalWeldDataSource


DEFAULT_TOPIC = "fabrica/linea1/soldadura"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulador PLC realista con tags NewData y handshake hacia MQTT."
    )
    parser.add_argument("--broker", default="localhost", help="Host MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Puerto MQTT")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Topic MQTT destino")
    parser.add_argument("--line-id", default="linea1", help="Identificador de linea")
    parser.add_argument(
        "--db-path",
        default="plc_reader_y_app/WeldParameters.db",
        help="SQLite historico usado como fuente primaria",
    )
    parser.add_argument(
        "--csv-path",
        default="plc_reader_y_app/WeldResults_10Feb_2026_24Feb_2026.csv",
        help="CSV historico usado como fallback",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=256,
        help="Cantidad de filas contiguas por ventana historica",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=4.0,
        help="Factor de aceleracion del ritmo historico",
    )
    parser.add_argument(
        "--timestamp-mode",
        choices=("now", "historical"),
        default="now",
        help="Usa tiempo actual para dashboard real-time o timestamp historico original",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cantidad maxima de lecturas a emitir antes de salir",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    source = HistoricalWeldDataSource(
        db_path=Path(args.db_path),
        csv_path=Path(args.csv_path),
    )
    tag_client = SimulatedTagClient()
    publisher = PahoMqttPublisher(args.broker, args.port)
    adapter = PlcMqttAdapter(
        tag_client=tag_client,
        publisher=publisher,
        topic=args.topic,
        line_id=args.line_id,
        source_type="plc_simulator",
        timestamp_mode=args.timestamp_mode,
    )
    producer = HistoricalPlcProducer(
        source=source,
        tag_client=tag_client,
        window_size=args.window_size,
        speed=args.speed,
    )

    adapter_thread = Thread(target=adapter.run_forever, daemon=True)
    adapter_thread.start()

    print(
        "Simulador PLC iniciado. "
        f"Fuente={source.backend}, MQTT={args.broker}:{args.port}, topic={args.topic}"
    )
    print("Presiona Ctrl+C para detener.")

    try:
        producer.run_forever(limit=args.limit)
    except KeyboardInterrupt:
        print("\nSimulador detenido.")
    finally:
        publisher.close()


if __name__ == "__main__":
    main()
