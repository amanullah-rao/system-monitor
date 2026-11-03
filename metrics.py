# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Readings that the taskbar strip and tray icons can show, in display order.

Names here are English and marked with N_; show them with tr(metric.name).
"""

from collections.abc import Callable
from dataclasses import dataclass

import formatting
from formatting import (
    format_bytes,
    format_duration,
    format_rate,
    format_temperature,
    rate_sample,
)
from i18n import N_
from system_monitor import SystemReading
from theme import ACCENT, GREEN, LIME, ORANGE, PINK, VIOLET

NORMAL, WARNING, CRITICAL = 0, 1, 2

TEMPERATURE_KEYS = ("cpu_temp", "gpu_temp")
RATE_KEYS = ("upload", "download")


@dataclass(frozen=True)
class MetricValue:
    text: str
    # Number drawn on a tray icon (0-100 also fills its bar); None when unavailable.
    number: float | None = None
    level: int = NORMAL
    # What the tray icon writes instead of `number`, such as a temperature in °F.
    tray_text: str | None = None


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    short: str
    sample: str
    accent: str
    read: Callable[[SystemReading], MetricValue]
    tray: bool = False

    def sample_text(self) -> str:
        """The widest value this can show, for sizing the taskbar strip."""
        if self.key in RATE_KEYS:
            return rate_sample()
        if self.key in TEMPERATURE_KEYS:
            return "212°F" if formatting.temperature_unit() == "F" else "100°C"
        return self.sample


def percent_level(percent: float) -> int:
    if percent >= 90:
        return CRITICAL
    if percent >= 75:
        return WARNING
    return NORMAL


def _percent(value: float | None) -> MetricValue:
    if value is None:
        return MetricValue("N/A")
    return MetricValue(f"{value:.0f}%", value, percent_level(value))


def _temperature(value: float | None, warning: float, critical: float) -> MetricValue:
    if value is None:
        return MetricValue("N/A")
    level = CRITICAL if value >= critical else WARNING if value >= warning else NORMAL
    shown = formatting.convert_temperature(value)
    return MetricValue(format_temperature(value), value, level, f"{shown:.0f}")


def _cpu_temperature(reading: SystemReading) -> MetricValue:
    return _temperature(reading.cpu_temperature_c, 70, 85)


def _gpu(reading: SystemReading) -> MetricValue:
    loads = [gpu.utilization for gpu in reading.gpus if gpu.utilization is not None]
    return _percent(sum(loads) / len(loads) if loads else None)


def _gpu_temperature(reading: SystemReading) -> MetricValue:
    """The hottest graphics card."""
    values = [gpu.temperature_c for gpu in reading.gpus if gpu.temperature_c is not None]
    return _temperature(max(values) if values else None, 75, 85)


def _disk_activity(reading: SystemReading) -> MetricValue:
    if reading.disk_read_bytes_per_s is None or reading.disk_write_bytes_per_s is None:
        return MetricValue("N/A")
    total = reading.disk_read_bytes_per_s + reading.disk_write_bytes_per_s
    return MetricValue(f"{format_bytes(total)}/s")


def _battery(reading: SystemReading) -> MetricValue:
    value = reading.battery_percent
    if value is None:
        return MetricValue("N/A")
    if reading.battery_plugged:
        return MetricValue(f"{value:.0f}% ⚡", value)
    level = CRITICAL if value <= 15 else WARNING if value <= 30 else NORMAL
    return MetricValue(f"{value:.0f}%", value, level)


def _battery_info(reading: SystemReading) -> MetricValue:
    """Time left on battery, or the charging power (where the laptop reports it)."""
    if reading.battery_percent is None:
        return MetricValue("N/A")
    power = reading.battery_power_w
    if reading.battery_plugged:
        return MetricValue(f"⚡ {abs(power):.1f} W" if power else "⚡")
    if reading.battery_seconds_left is not None:
        return MetricValue(format_duration(reading.battery_seconds_left))
    return MetricValue(f"{abs(power):.1f} W" if power else "N/A")


METRICS: tuple[Metric, ...] = (
    Metric("upload", N_("Upload speed"), "↑", "1023.9 KB/s", ACCENT,
           lambda r: MetricValue(format_rate(r.network_sent_mbps))),
    Metric("download", N_("Download speed"), "↓", "1023.9 KB/s", GREEN,
           lambda r: MetricValue(format_rate(r.network_received_mbps))),
    Metric("cpu", N_("CPU usage"), "CPU", "100%", ACCENT,
           lambda r: _percent(r.cpu_percent), tray=True),
    Metric("ram", N_("Memory (RAM)"), "RAM", "100%", GREEN,
           lambda r: _percent(r.memory_percent), tray=True),
    Metric("cpu_temp", N_("CPU temperature"), "TEMP", "100°C", ORANGE,
           _cpu_temperature, tray=True),
    Metric("gpu", N_("GPU usage"), "GPU", "100%", VIOLET, _gpu, tray=True),
    Metric("gpu_temp", N_("GPU temperature"), "GPU°", "100°C", ORANGE,
           _gpu_temperature, tray=True),
    Metric("disk", N_("Drive space used"), "DISK", "100%", PINK,
           lambda r: _percent(r.disk_percent), tray=True),
    Metric("disk_io", N_("Disk activity"), "I/O", "1023.9 MB/s", PINK, _disk_activity),
    Metric("battery", N_("Battery"), "BAT", "100% ⚡", LIME, _battery, tray=True),
    Metric("battery_info", N_("Battery time left or charging power"), "LEFT",
           "⚡ 99.9 W", LIME, _battery_info),
    Metric("uptime", N_("Time since start-up"), "UP", "99d 23h", ACCENT,
           lambda r: MetricValue(format_duration(r.uptime_seconds))),
    Metric("data_today", N_("Data used today"), "TODAY", "1023.9 MB", VIOLET,
           lambda r: MetricValue(format_bytes(r.data_today_received + r.data_today_sent))),
    Metric("data_month", N_("Data used this month"), "MONTH", "1023.9 MB", VIOLET,
           lambda r: MetricValue(format_bytes(r.data_month_received + r.data_month_sent))),
)

METRICS_BY_KEY = {metric.key: metric for metric in METRICS}
TRAY_METRICS = tuple(metric for metric in METRICS if metric.tray)
# What the single tray icon can show: the app logo, or one live reading.
# Labels are English; show them with tr().
TRAY_ICON_CHOICES: tuple[tuple[str, str], ...] = (("logo", N_("App logo")),) + tuple(
    (metric.key, metric.name) for metric in TRAY_METRICS
)


def ordered(keys: list[str], metrics: tuple[Metric, ...] = METRICS) -> list[Metric]:
    """Selected metrics in catalog order."""
    selected = set(keys)
    return [metric for metric in metrics if metric.key in selected]


def in_order(keys: list[str]) -> list[Metric]:
    """Selected metrics in the order the user arranged them."""
    seen = set()
    result = []
    for key in keys:
        if key in METRICS_BY_KEY and key not in seen:
            seen.add(key)
            result.append(METRICS_BY_KEY[key])
    return result


# One-click arrangements for the taskbar strip, in display order. Names are
# English; show them with tr().
STRIP_PRESETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (N_("Internet speed"), ("download", "upload")),
    (N_("Speed + CPU/RAM"), ("upload", "download", "cpu", "ram")),
    (N_("Performance"), ("cpu", "cpu_temp", "ram", "gpu")),
    (N_("Temperatures"), ("cpu_temp", "gpu_temp", "cpu", "gpu")),
    (N_("Data usage"), ("download", "upload", "data_today", "data_month")),
    (N_("Everything"), tuple(metric.key for metric in METRICS)),
)


def preview_values() -> dict[str, str]:
    """Typical values for the layout preview, in the chosen units."""
    megabits = lambda kilobytes: kilobytes * 1024 * 8 / 1_000_000  # noqa: E731
    return {
        "upload": format_rate(megabits(48.2)),
        "download": format_rate(megabits(1331)),
        "cpu": "23%",
        "ram": "47%",
        "cpu_temp": format_temperature(56),
        "gpu": "31%",
        "gpu_temp": format_temperature(48),
        "disk": "61%",
        "disk_io": "2.4 MB/s",
        "battery": "87%",
        "battery_info": "2h 10m",
        "uptime": format_duration(3 * 3600 + 12 * 60),
        "data_today": "1.4 GB",
        "data_month": "38.6 GB",
    }
