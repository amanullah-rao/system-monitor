# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Smaller readings: drives, per-adapter network speed and battery power."""

import ctypes
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass

import psutil

from sensor_app import SESSION_ENDING

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


@dataclass(frozen=True)
class DriveReading:
    mount: str  # such as "C:\\"
    label: str  # the volume name; may be empty
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


@dataclass(frozen=True)
class AdapterReading:
    name: str
    sent_mbps: float
    received_mbps: float


def _volume_label(mount: str) -> str:
    if os.name != "nt":
        return ""
    name = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(mount), name, len(name), None, None, None, None, 0
    )
    return name.value if ok else ""


class DriveCollector:
    """Every fixed and removable drive, looked up every few seconds.

    Drive space barely changes, and waking a sleeping disk for it twice a
    second would be wasteful.
    """

    INTERVAL_SECONDS = 5

    def __init__(self) -> None:
        self._drives: tuple[DriveReading, ...] = ()
        self._last = -float("inf")
        self._labels: dict[str, str] = {}

    def read(self) -> tuple[DriveReading, ...]:
        if time.monotonic() - self._last < self.INTERVAL_SECONDS:
            return self._drives
        self._last = time.monotonic()
        drives = []
        try:
            partitions = psutil.disk_partitions(all=False)
        except (OSError, RuntimeError):
            return self._drives
        for partition in partitions:
            options = partition.opts.lower()
            if "cdrom" in options or not ("fixed" in options or "removable" in options):
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except OSError:  # an empty card reader, or a drive that went away
                continue
            if usage.total <= 0:
                continue
            if partition.mountpoint not in self._labels:
                self._labels[partition.mountpoint] = _volume_label(partition.mountpoint)
            drives.append(
                DriveReading(
                    mount=partition.mountpoint,
                    label=self._labels[partition.mountpoint],
                    total_gb=usage.total / 1024**3,
                    used_gb=usage.used / 1024**3,
                    free_gb=usage.free / 1024**3,
                    percent=float(usage.percent),
                )
            )
        self._drives = tuple(drives)
        return self._drives


class AdapterRates:
    """Download and upload speed of each connected network adapter."""

    LIMIT = 4
    # Skips virtual adapters that have never carried anything.
    MIN_TOTAL_BYTES = 1_000_000

    def __init__(self) -> None:
        self._previous: dict[str, tuple[int, int]] = {}
        self._previous_time = time.monotonic()
        self._up: dict[str, bool] = {}
        self._up_checked = -float("inf")

    def _connected(self) -> dict[str, bool]:
        # Link state rarely changes, and this call is slower than the counters.
        if time.monotonic() - self._up_checked >= 5:
            try:
                self._up = {name: stat.isup for name, stat in psutil.net_if_stats().items()}
            except (OSError, RuntimeError):
                pass
            self._up_checked = time.monotonic()
        return self._up

    def read(self) -> tuple[AdapterReading, ...]:
        now = time.monotonic()
        elapsed = max(now - self._previous_time, 0.001)
        try:
            counters = psutil.net_io_counters(pernic=True)
        except (OSError, RuntimeError):
            return ()
        up = self._connected()
        found = []
        current = {}
        for name, counter in counters.items():
            current[name] = (counter.bytes_sent, counter.bytes_recv)
            if name.lower().startswith("loopback") or name.lower() == "lo":
                continue
            previous = self._previous.get(name)
            if previous is None or not up.get(name, False):
                continue
            sent = max(0, counter.bytes_sent - previous[0])
            received = max(0, counter.bytes_recv - previous[1])
            total = counter.bytes_sent + counter.bytes_recv
            if sent + received == 0 and total < self.MIN_TOTAL_BYTES:
                continue
            found.append(
                AdapterReading(
                    name=name,
                    sent_mbps=sent * 8 / elapsed / 1_000_000,
                    received_mbps=received * 8 / elapsed / 1_000_000,
                )
            )
        self._previous = current
        self._previous_time = now
        found.sort(key=lambda a: a.sent_mbps + a.received_mbps, reverse=True)
        return tuple(found[: self.LIMIT])


UNKNOWN_RATE = 0x80000000  # what Windows reports when the battery can't say


def parse_battery_status(text: str) -> float | None:
    """Watts from Windows' BatteryStatus: positive charging, negative discharging."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return None

    def milliwatts(key: str) -> float | None:
        try:
            value = float(data.get(key))
        except (TypeError, ValueError):
            return None
        return value if 0 < value < UNKNOWN_RATE else None

    charge, discharge = milliwatts("ChargeRate"), milliwatts("DischargeRate")
    if data.get("Charging") and charge is not None:
        return charge / 1000
    if data.get("Discharging") and discharge is not None:
        return -discharge / 1000
    return None


class BatteryCollector:
    """Charging or discharging power, which psutil doesn't report.

    Windows exposes it through WMI on many laptops; it's read every few
    seconds on a background thread, and stays None where it isn't available.
    """

    INTERVAL_SECONDS = 10
    COMMAND = (
        "$s = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus "
        "-ErrorAction Stop | Select-Object -First 1 ChargeRate, DischargeRate, "
        "Charging, Discharging; ConvertTo-Json -InputObject $s -Compress"
    )

    def __init__(self) -> None:
        self._power: float | None = None
        self._last = -float("inf")
        self._running = False
        self._lock = threading.Lock()

    def read(self, has_battery: bool) -> float | None:
        if not has_battery or os.name != "nt":
            return None
        with self._lock:
            due = time.monotonic() - self._last >= self.INTERVAL_SECONDS
            if due and not self._running and not SESSION_ENDING.is_set():
                self._running = True
                self._last = time.monotonic()
                threading.Thread(target=self._poll, daemon=True).start()
            return self._power

    def _poll(self) -> None:
        power = None
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", self.COMMAND],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=NO_WINDOW,
            )
            power = parse_battery_status(result.stdout)
        except (OSError, subprocess.SubprocessError):
            pass
        finally:
            with self._lock:
                self._power = power
                self._running = False


def battery_seconds_left(battery) -> float | None:
    """Time left on battery in seconds; None while plugged in or unknown."""
    if battery is None or battery.power_plugged:
        return None
    seconds = battery.secsleft
    return float(seconds) if isinstance(seconds, (int, float)) and seconds >= 0 else None
