# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

from PySide6.QtCore import QObject, Signal

from formatting import format_gb
from system_monitor import SystemReading

HIGH_USAGE_PERCENT = 90
HIGH_USAGE_SECONDS = 30
REPEAT_AFTER_SECONDS = 10 * 60
LOW_DISK_FREE_PERCENT = 10
LOW_BATTERY_PERCENT = 15


class UsageAlerts(QObject):
    """Turn sustained problems into short notifications, without repeating them."""

    alert = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._high_since: dict[str, float] = {}
        self._last_alert: dict[str, float] = {}
        self._disk_warned = False
        self._battery_warned = False

    def check(self, reading: SystemReading) -> None:
        now = reading.timestamp
        top = reading.processes[0] if reading.processes else None
        cpu_hint = (
            f" {top.name} is using the most ({top.cpu_percent:.0f}%)."
            if top is not None
            else ""
        )
        self._check_sustained(
            "cpu",
            reading.cpu_percent,
            now,
            "Your processor is very busy",
            f"CPU has been above {HIGH_USAGE_PERCENT}% for "
            f"{HIGH_USAGE_SECONDS} seconds.{cpu_hint}",
        )
        self._check_sustained(
            "ram",
            reading.memory_percent,
            now,
            "Memory is almost full",
            f"{format_gb(reading.memory_available_gb)} of RAM is left. "
            "Closing unused apps can help.",
        )

        if reading.disk_percent is not None and reading.disk_free_gb is not None:
            low = 100 - reading.disk_percent < LOW_DISK_FREE_PERCENT
            if low and not self._disk_warned:
                self.alert.emit(
                    f"Drive {reading.disk_name} is almost full",
                    f"Only {format_gb(reading.disk_free_gb)} free. "
                    "Windows may slow down when the drive is full.",
                )
            self._disk_warned = low

        if reading.battery_percent is not None:
            low = (
                not reading.battery_plugged
                and reading.battery_percent <= LOW_BATTERY_PERCENT
            )
            if low and not self._battery_warned:
                self.alert.emit(
                    "Battery is low",
                    f"{reading.battery_percent:.0f}% left. Plug in your charger soon.",
                )
            self._battery_warned = low

    def _check_sustained(
        self, key: str, percent: float, now: float, title: str, message: str
    ) -> None:
        if percent < HIGH_USAGE_PERCENT:
            self._high_since.pop(key, None)
            return
        since = self._high_since.setdefault(key, now)
        recently_alerted = now - self._last_alert.get(key, -REPEAT_AFTER_SECONDS) < (
            REPEAT_AFTER_SECONDS
        )
        if now - since >= HIGH_USAGE_SECONDS and not recently_alerted:
            self._last_alert[key] = now
            self.alert.emit(title, message)
