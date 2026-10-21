# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

def format_temperature(value: float | None, missing: str = "—") -> str:
    return f"{value:.0f}°C" if value is not None else missing


def format_bytes(count: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if count < 1024:
            return f"{count:.0f} {unit}" if unit == "B" else f"{count:.1f} {unit}"
        count /= 1024
    return f"{count:.1f} TB"


def format_rate(mbps: float) -> str:
    return f"{format_bytes(mbps * 1_000_000 / 8)}/s"


def format_duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_gb(value: float) -> str:
    return f"{value:.1f} GB" if value < 100 else f"{value:.0f} GB"
