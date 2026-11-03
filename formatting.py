# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

from i18n import tr

# Display preferences, set once at start-up and when the user changes them.
# Readings themselves are always kept in bytes and °C.
_speed_unit = "bytes"  # "bytes" (KB/s, MB/s) or "bits" (Kbps, Mbps)
_temperature_unit = "C"  # "C" or "F"


def set_speed_unit(unit: str) -> None:
    global _speed_unit
    _speed_unit = "bits" if unit == "bits" else "bytes"


def set_temperature_unit(unit: str) -> None:
    global _temperature_unit
    _temperature_unit = "F" if unit == "F" else "C"


def temperature_unit() -> str:
    return _temperature_unit


def convert_temperature(celsius: float) -> float:
    return celsius * 9 / 5 + 32 if _temperature_unit == "F" else celsius


def format_temperature(value: float | None, missing: str = "—") -> str:
    if value is None:
        return missing
    return f"{convert_temperature(value):.0f}°{_temperature_unit}"


def format_bytes(count: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024:
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} TB"


def format_rate(mbps: float) -> str:
    """A network speed given in megabits per second, in the chosen unit."""
    if _speed_unit == "bits":
        bits = mbps * 1_000_000
        for factor, unit in ((1e9, "Gbps"), (1e6, "Mbps"), (1e3, "Kbps")):
            if bits >= factor:
                return f"{bits / factor:.1f} {unit}"
        return f"{bits:.0f} bps"
    return f"{format_bytes(mbps * 1_000_000 / 8)}/s"


def rate_sample() -> str:
    """The widest speed text, for sizing the taskbar strip."""
    return "999.9 Mbps" if _speed_unit == "bits" else "1023.9 KB/s"


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return tr("{d}d {h}h").format(d=days, h=hours)
    if hours:
        return tr("{h}h {m}m").format(h=hours, m=minutes)
    return tr("{m}m").format(m=minutes)


def format_gb(value: float) -> str:
    return f"{value:.1f} GB" if value < 100 else f"{value:.0f} GB"
