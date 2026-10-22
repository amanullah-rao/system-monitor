# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""A plain-text report of what the app can and can't read, for bug reports.

It holds hardware and sensor details only: no user names, folder paths or
anything else personal.
"""

import platform
import sys

import app_info
from formatting import format_temperature
from sensor_app import HELPER_TASK, LHM_TASK, pawnio_installed, read_helper_output, task_exists
from system_monitor import SystemReading

try:
    import winreg
except ImportError:  # Not on Windows.
    winreg = None


def _processor_name() -> str:
    if winreg is not None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def collect(reading: SystemReading | None) -> str:
    lines = [
        f"{app_info.APP_NAME} {app_info.VERSION} "
        f"({'installed app' if getattr(sys, 'frozen', False) else 'from source'})",
        f"Windows: {platform.platform()} ({platform.machine()})",
        f"Processor: {_processor_name()}",
        "",
        "CPU temperature:",
        f"  Sensor task ({HELPER_TASK}): "
        f"{'installed' if task_exists(HELPER_TASK) else 'missing'}",
        f"  LibreHardwareMonitor task: {'installed' if task_exists(LHM_TASK) else 'none'}",
        f"  PawnIO driver: {'installed' if pawnio_installed() else 'missing'}",
    ]
    helper = read_helper_output()
    if helper is None:
        lines.append("  Sensor reader: not running")
    else:
        sensors = helper.get("temperatures") or []
        lines.append(f"  Sensor reader: running, {len(sensors)} temperature sensors")
        for sensor in sensors[:40]:
            if isinstance(sensor, dict):
                hardware = sensor.get("hardware", "Cpu")
                device = sensor.get("device", "")
                lines.append(
                    f"    {hardware} {device}: {sensor.get('name')} = {sensor.get('value')}"
                )
    if reading is not None:
        lines.append(
            f"  Shown: {format_temperature(reading.cpu_temperature_c, 'not available')}"
            f" ({reading.cpu_temperature_status})"
        )
        lines += ["", "Graphics:", f"  {reading.gpu_status}"]
        for gpu in reading.gpus:
            load = f"{gpu.utilization:.0f}%" if gpu.utilization is not None else "no load data"
            temperature = format_temperature(gpu.temperature_c, "no temperature")
            error = f" ({gpu.error})" if gpu.error else ""
            lines.append(f"  {gpu.name}: {load}, {temperature}{error}")
    return "\n".join(lines)
