from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock


@dataclass
class PalletRunState:
    run_id: str
    last_seen: datetime
    slots: set[tuple[str, str]] = field(default_factory=set)
    complete: bool = False


class PalletRunTracker:
    """Creates a unique run id for each physical pallet pass through the cell."""

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout = timedelta(seconds=timeout_seconds)
        self._runs: dict[str, PalletRunState] = {}
        self._sequence = 0
        self._lock = RLock()

    def assign(
        self,
        pallet_id: str,
        real_station: str,
        schedule: str,
        observed_at: datetime,
    ) -> str:
        pallet_key = str(pallet_id)
        slot = (str(real_station), str(schedule))

        with self._lock:
            state = self._runs.get(pallet_key)
            if self._needs_new_run(state, observed_at):
                state = self._new_run(pallet_key, observed_at)
                self._runs[pallet_key] = state

            state.slots.add(slot)
            state.last_seen = observed_at
            if len(state.slots) >= 8:
                state.complete = True

            return state.run_id

    def _needs_new_run(
        self,
        state: PalletRunState | None,
        observed_at: datetime,
    ) -> bool:
        if state is None:
            return True
        if state.complete:
            return True
        return observed_at - state.last_seen > self.timeout

    def _new_run(self, pallet_id: str, observed_at: datetime) -> PalletRunState:
        self._sequence += 1
        safe_pallet = re.sub(r"[^A-Za-z0-9_-]+", "_", str(pallet_id)).strip("_")
        if not safe_pallet:
            safe_pallet = "unknown"
        run_id = f"{safe_pallet}-{observed_at.strftime('%Y%m%dT%H%M%S')}-{self._sequence:04d}"
        return PalletRunState(run_id=run_id, last_seen=observed_at)
