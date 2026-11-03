# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

from datetime import datetime

from PySide6.QtCore import QObject, Signal

from formatting import format_bytes, format_gb
from i18n import tr
from system_monitor import SystemReading

HIGH_USAGE_SECONDS = 30
REPEAT_AFTER_SECONDS = 10 * 60
# Percent of the monthly data limit at which the first warning appears.
DATA_LIMIT_WARNING_PERCENT = 80


class UsageAlerts(QObject):
    """Turn sustained problems into short notifications, without repeating them."""

    alert = Signal(str, str)
    # The marker to remember so a data limit warning isn't repeated, such as
    # "2026-11:80" (month and percent level).
    data_notice_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._high_since: dict[str, float] = {}
        self._last_alert: dict[str, float] = {}
        self._low_drives: set[str] = set()
        self._battery_warned = False
        self.cpu_percent = 90
        self.ram_percent = 90
        self.drive_free_percent = 10
        self.battery_percent = 15
        self.data_limit_bytes = 0
        self.data_notice = ""

    def configure(
        self,
        cpu_percent: int,
        ram_percent: int,
        drive_free_percent: int,
        battery_percent: int,
        data_limit_gb: int,
        data_notice: str,
    ) -> None:
        self.cpu_percent = cpu_percent
        self.ram_percent = ram_percent
        self.drive_free_percent = drive_free_percent
        self.battery_percent = battery_percent
        self.data_limit_bytes = max(0, data_limit_gb) * 1024**3
        self.data_notice = data_notice

    def check(self, reading: SystemReading) -> None:
        now = reading.timestamp
        top = reading.processes[0] if reading.processes else None
        cpu_hint = (
            " " + tr("{name} is using the most ({percent}%).").format(
                name=top.name, percent=f"{top.cpu_percent:.0f}"
            )
            if top is not None and top.cpu_percent >= 10
            else ""
        )
        self._check_sustained(
            "cpu",
            reading.cpu_percent,
            self.cpu_percent,
            now,
            tr("Your processor is very busy"),
            tr("CPU has been above {percent}% for {seconds} seconds.").format(
                percent=self.cpu_percent, seconds=HIGH_USAGE_SECONDS
            )
            + cpu_hint,
        )
        self._check_sustained(
            "ram",
            reading.memory_percent,
            self.ram_percent,
            now,
            tr("Memory is almost full"),
            tr("{free} of RAM is left. Closing unused apps can help.").format(
                free=format_gb(reading.memory_available_gb)
            ),
        )
        self._check_drives(reading)
        self._check_battery(reading)
        self._check_data_limit(reading)

    def _check_drives(self, reading: SystemReading) -> None:
        drives = [
            (drive.mount, drive.percent, drive.free_gb) for drive in reading.drives
        ]
        if not drives and reading.disk_percent is not None and reading.disk_free_gb is not None:
            drives = [(reading.disk_name, reading.disk_percent, reading.disk_free_gb)]
        for mount, percent, free_gb in drives:
            low = 100 - percent < self.drive_free_percent
            if low and mount not in self._low_drives:
                self.alert.emit(
                    tr("Drive {drive} is almost full").format(drive=mount),
                    tr(
                        "Only {free} free. Windows may slow down when the drive is full."
                    ).format(free=format_gb(free_gb)),
                )
            if low:
                self._low_drives.add(mount)
            else:
                self._low_drives.discard(mount)

    def _check_battery(self, reading: SystemReading) -> None:
        if reading.battery_percent is None:
            return
        low = (
            not reading.battery_plugged
            and reading.battery_percent <= self.battery_percent
        )
        if low and not self._battery_warned:
            self.alert.emit(
                tr("Battery is low"),
                tr("{percent}% left. Plug in your charger soon.").format(
                    percent=f"{reading.battery_percent:.0f}"
                ),
            )
        self._battery_warned = low

    def _check_data_limit(self, reading: SystemReading) -> None:
        if self.data_limit_bytes <= 0:
            return
        used = reading.data_month_received + reading.data_month_sent
        percent = used / self.data_limit_bytes * 100
        level = 100 if percent >= 100 else DATA_LIMIT_WARNING_PERCENT if (
            percent >= DATA_LIMIT_WARNING_PERCENT
        ) else 0
        if level == 0:
            return
        month = datetime.fromtimestamp(reading.timestamp).strftime("%Y-%m")
        last_month, _, last_level = self.data_notice.partition(":")
        already = last_month == month and last_level.isdigit() and int(last_level) >= level
        if already:
            return
        self.data_notice = f"{month}:{level}"
        self.data_notice_changed.emit(self.data_notice)
        limit = format_gb(self.data_limit_bytes / 1024**3)
        if level == 100:
            self.alert.emit(
                tr("Internet data limit reached"),
                tr("You've used {used} this month, over your {limit} limit.").format(
                    used=format_bytes(used), limit=limit
                ),
            )
        else:
            self.alert.emit(
                tr("Internet data: {percent}% of your limit used").format(
                    percent=DATA_LIMIT_WARNING_PERCENT
                ),
                tr("You've used {used} of your {limit} monthly limit.").format(
                    used=format_bytes(used), limit=limit
                ),
            )

    def _check_sustained(
        self,
        key: str,
        percent: float,
        threshold: float,
        now: float,
        title: str,
        message: str,
    ) -> None:
        if percent < threshold:
            self._high_since.pop(key, None)
            return
        since = self._high_since.setdefault(key, now)
        recently_alerted = now - self._last_alert.get(key, -REPEAT_AFTER_SECONDS) < (
            REPEAT_AFTER_SECONDS
        )
        if now - since >= HIGH_USAGE_SECONDS and not recently_alerted:
            self._last_alert[key] = now
            self.alert.emit(title, message)
