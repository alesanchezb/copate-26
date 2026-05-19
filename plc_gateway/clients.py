from __future__ import annotations

from dataclasses import dataclass
from threading import Condition, RLock
from typing import Any, Protocol


@dataclass(frozen=True)
class TagReadResult:
    Value: Any
    Status: str = "Success"


class TagClient(Protocol):
    def read(self, plc_ip: str, tag: str) -> TagReadResult:
        ...

    def write(self, plc_ip: str, tag: str, value: Any) -> Any:
        ...


class SimulatedTagClient:
    """Thread-safe in-memory tag table with PLC-like read/write semantics."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], Any] = {}
        self._metadata: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = RLock()
        self._condition = Condition(self._lock)

    def read(self, plc_ip: str, tag: str) -> TagReadResult:
        with self._lock:
            return TagReadResult(self._values.get((str(plc_ip), str(tag)), 0))

    def write(self, plc_ip: str, tag: str, value: Any) -> TagReadResult:
        with self._condition:
            self._values[(str(plc_ip), str(tag))] = value
            self._condition.notify_all()
            return TagReadResult(value)

    def write_many(self, plc_ip: str, values: dict[str, Any]) -> None:
        with self._condition:
            for tag, value in values.items():
                self._values[(str(plc_ip), str(tag))] = value
            self._condition.notify_all()

    def wait_for_value(
        self,
        plc_ip: str,
        tag: str,
        expected: Any,
        timeout_seconds: float,
    ) -> bool:
        key = (str(plc_ip), str(tag))
        with self._condition:
            return self._condition.wait_for(
                lambda: self._values.get(key) == expected,
                timeout=timeout_seconds,
            )

    def set_metadata(self, plc_ip: str, tag: str, metadata: dict[str, Any]) -> None:
        with self._lock:
            self._metadata[(str(plc_ip), str(tag))] = dict(metadata)

    def get_metadata(self, plc_ip: str, tag: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._metadata.get((str(plc_ip), str(tag)), {}))

    def clear_metadata(self, plc_ip: str, tag: str) -> None:
        with self._lock:
            self._metadata.pop((str(plc_ip), str(tag)), None)


class PylogixTagClient:
    """Future production client that exposes the same interface as the simulator."""

    def __init__(self) -> None:
        self._connections: dict[str, Any] = {}
        self._lock = RLock()

    def _connection(self, plc_ip: str) -> Any:
        with self._lock:
            if plc_ip not in self._connections:
                try:
                    from pylogix import PLC
                except ImportError as exc:
                    raise RuntimeError(
                        "pylogix no esta instalado. Instalalo solo en el host que lea PLC real."
                    ) from exc

                comm = PLC()
                comm.IPAddress = plc_ip
                self._connections[plc_ip] = comm
            return self._connections[plc_ip]

    def read(self, plc_ip: str, tag: str) -> Any:
        return self._connection(str(plc_ip)).Read(str(tag))

    def write(self, plc_ip: str, tag: str, value: Any) -> Any:
        return self._connection(str(plc_ip)).Write(str(tag), value)

    def close(self) -> None:
        with self._lock:
            for comm in self._connections.values():
                close = getattr(comm, "Close", None)
                if callable(close):
                    close()
            self._connections.clear()
