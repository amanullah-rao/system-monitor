# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Internet data used per day, counted while the app runs."""

import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

# Days of history kept; older days are dropped when saving.
KEEP_DAYS = 400
SAVE_EVERY_SECONDS = 60


def usage_file() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "System Monitor" / "data_usage.json"


class DataUsageTracker:
    """Received and sent bytes per local calendar day, saved to a small JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or usage_file()
        # "2026-10-21": [received, sent]
        self._days: dict[str, list[int]] = self._load()
        self._dirty = False
        self._last_save = time.monotonic()

    def _load(self) -> dict[str, list[int]]:
        try:
            days = json.loads(self._path.read_text(encoding="utf-8"))["days"]
            return {str(day): [int(value[0]), int(value[1])] for day, value in days.items()}
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return {}

    def add(self, received: int, sent: int, today: date | None = None) -> None:
        if received <= 0 and sent <= 0:
            return
        day = self._days.setdefault((today or date.today()).isoformat(), [0, 0])
        day[0] += max(0, received)
        day[1] += max(0, sent)
        self._dirty = True
        if time.monotonic() - self._last_save >= SAVE_EVERY_SECONDS:
            self.save(today)

    def today(self, today: date | None = None) -> tuple[int, int]:
        received, sent = self._days.get((today or date.today()).isoformat(), (0, 0))
        return received, sent

    def month(self, today: date | None = None) -> tuple[int, int]:
        prefix = (today or date.today()).isoformat()[:7]
        days = [value for day, value in self._days.items() if day.startswith(prefix)]
        return sum(day[0] for day in days), sum(day[1] for day in days)

    def save(self, today: date | None = None) -> None:
        if not self._dirty:
            return
        # Counted as an attempt even if it fails, so a read-only folder
        # isn't retried on every sample.
        self._last_save = time.monotonic()
        cutoff = ((today or date.today()) - timedelta(days=KEEP_DAYS)).isoformat()
        self._days = {day: value for day, value in self._days.items() if day >= cutoff}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"days": self._days}), encoding="utf-8")
            os.replace(temporary, self._path)
        except OSError:
            return
        self._dirty = False
