from __future__ import annotations

import argparse
import logging

from plc_gateway.adapter import PahoMqttPublisher, PlcMqttAdapter
from plc_gateway.clients import PylogixTagClient


DEFAULT_TOPIC = "fabrica/linea1/soldadura"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Adapter de PLC real a MQTT para la celda de soldadura."
    )
    parser.add_argument("--broker", default="localhost", help="Host o IP del broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Puerto MQTT")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Topic MQTT destino")
    parser.add_argument("--line-id", default="linea1", help="Identificador de linea")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Segundos entre barridos de tags NewData",
    )
    parser.add_argument(
        "--handshake-pulse",
        type=float,
        default=0.25,
        help="Segundos que el ack HndShk permanece en 1 antes de volver a 0",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    tag_client = PylogixTagClient()
    publisher = PahoMqttPublisher(args.broker, args.port)
    adapter = PlcMqttAdapter(
        tag_client=tag_client,
        publisher=publisher,
        topic=args.topic,
        line_id=args.line_id,
        source_type="plc_real",
        poll_interval_seconds=args.poll_interval,
        handshake_pulse_seconds=args.handshake_pulse,
        timestamp_mode="now",
    )

    print(
        "Adapter PLC real iniciado. "
        f"MQTT={args.broker}:{args.port}, topic={args.topic}, line_id={args.line_id}"
    )
    print("Presiona Ctrl+C para detener.")

    try:
        adapter.run_forever()
    except KeyboardInterrupt:
        print("\nAdapter PLC detenido.")
    finally:
        publisher.close()
        tag_client.close()


if __name__ == "__main__":
    main()
