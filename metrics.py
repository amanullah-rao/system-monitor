# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Readings that the taskbar strip and tray icons can show, in display order."""

from collections.abc import Callable
from dataclasses import dataclass

from formatting import format_bytes, format_duration, format_rate, format_temperature
from system_monitor import SystemReading
from theme import ACCENT, GREEN, LIME, ORANGE, PINK, VIOLET

NORMAL, WARNING, CRITICAL = 0, 1, 2


@dataclass(frozen=True)
class MetricValue:
    text: str
    # Number drawn on a tray icon (0-100 also fills its bar); None when unavailable.
    number: float | None = None
    level: int = NORMAL


@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    short: str
    sample: str
    accent: str
    read: Callable[[SystemReading], MetricValue]
    tray: bool = False


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


def _cpu_temperature(reading: SystemReading) -> MetricValue:
    value = reading.cpu_temperature_c
    if value is None:
        return MetricValue("N/A")
    level = CRITICAL if value >= 85 else WARNING if value >= 70 else NORMAL
    return MetricValue(format_temperature(value), value, level)


def _gpu(reading: SystemReading) -> MetricValue:
    loads = [gpu.utilization for gpu in reading.gpus if gpu.utilization is not None]
    return _percent(sum(loads) / len(loads) if loads else None)


def _gpu_temperature(reading: SystemReading) -> MetricValue:
    """The hottest graphics card."""
    values = [gpu.temperature_c for gpu in reading.gpus if gpu.temperature_c is not None]
    if not values:
        return MetricValue("N/A")
    value = max(values)
    level = CRITICAL if value >= 85 else WARNING if value >= 75 else NORMAL
    return MetricValue(format_temperature(value), value, level)


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


METRICS: tuple[Metric, ...] = (
    Metric("upload", "Upload speed", "↑", "1023.9 KB/s", ACCENT,
           lambda r: MetricValue(format_rate(r.network_sent_mbps))),
    Metric("download", "Download speed", "↓", "1023.9 KB/s", GREEN,
           lambda r: MetricValue(format_rate(r.network_received_mbps))),
    Metric("cpu", "CPU usage", "CPU", "100%", ACCENT,
           lambda r: _percent(r.cpu_percent), tray=True),
    Metric("ram", "Memory (RAM)", "RAM", "100%", GREEN,
           lambda r: _percent(r.memory_percent), tray=True),
    Metric("cpu_temp", "CPU temperature", "TEMP", "100°C", ORANGE,
           _cpu_temperature, tray=True),
    Metric("gpu", "GPU usage", "GPU", "100%", VIOLET, _gpu, tray=True),
    Metric("gpu_temp", "GPU temperature", "GPU°", "100°C", ORANGE,
           _gpu_temperature, tray=True),
    Metric("disk", "Drive space used", "DISK", "100%", PINK,
           lambda r: _percent(r.disk_percent), tray=True),
    Metric("disk_io", "Disk activity", "I/O", "1023.9 MB/s", PINK, _disk_activity),
    Metric("battery", "Battery", "BAT", "100% ⚡", LIME, _battery, tray=True),
    Metric("uptime", "Time since start-up", "UP", "99d 23h", ACCENT,
           lambda r: MetricValue(format_duration(r.uptime_seconds))),
    Metric("data_today", "Data used today", "TODAY", "1023.9 MB", VIOLET,
           lambda r: MetricValue(format_bytes(r.data_today_received + r.data_today_sent))),
    Metric("data_month", "Data used this month", "MONTH", "1023.9 MB", VIOLET,
           lambda r: MetricValue(format_bytes(r.data_month_received + r.data_month_sent))),
)

METRICS_BY_KEY = {metric.key: metric for metric in METRICS}
TRAY_METRICS = tuple(metric for metric in METRICS if metric.tray)
# What the single tray icon can show: the app logo, or one live reading.
TRAY_ICON_CHOICES: tuple[tuple[str, str], ...] = (("logo", "App logo"),) + tuple(
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


# One-click arrangements for the taskbar strip, in display order.
STRIP_PRESETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Internet speed", ("download", "upload")),
    ("Speed + CPU/RAM", ("upload", "download", "cpu", "ram")),
    ("Performance", ("cpu", "cpu_temp", "ram", "gpu")),
    ("Temperatures", ("cpu_temp", "gpu_temp", "cpu", "gpu")),
    ("Data usage", ("download", "upload", "data_today", "data_month")),
    ("Everything", tuple(metric.key for metric in METRICS)),
)

# Typical values for the layout preview in Settings.
PREVIEW_VALUES = {
    "upload": "48.2 KB/s",
    "download": "1.3 MB/s",
    "cpu": "23%",
    "ram": "47%",
    "cpu_temp": "56°C",
    "gpu": "31%",
    "gpu_temp": "48°C",
    "disk": "61%",
    "disk_io": "2.4 MB/s",
    "battery": "87%",
    "uptime": "3h 12m",
    "data_today": "1.4 GB",
    "data_month": "38.6 GB",
}
