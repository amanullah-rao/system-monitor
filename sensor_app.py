# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Start and stop the CPU temperature source together with System Monitor.

Reading CPU temperature needs administrator rights, so the source runs from a
Task Scheduler task set to "Run with highest privileges": the signed-in user
may run and end their own task without a UAC prompt.

Preferred source: the windowless sensor helper installed by sensor_setup.ps1
(task "SystemMonitorSensors"). Fallback: the LibreHardwareMonitor app (task
"LibreHardwareMonitor"), which shows its own tray icon.
"""

import json
import os
import subprocess
import threading
import time
from pathlib import Path

import psutil

HELPER_TASK = "SystemMonitorSensors"
LHM_TASK = "LibreHardwareMonitor"
LHM_PROCESS = "librehardwaremonitor.exe"
HELPER_OUTPUT = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "SystemMonitor" / "sensors.json"
# The helper rewrites its file every second; older than this means it stopped.
FRESH_SECONDS = 5
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _schtasks(*args: str) -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["schtasks", *args],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def read_helper_output() -> dict | None:
    """The helper's latest data, or None if it isn't running."""
    try:
        data = json.loads(HELPER_OUTPUT.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if time.time() - float(data.get("updated", 0)) > FRESH_SECONDS:
        return None
    return data


def _lhm_running() -> bool:
    for process in psutil.process_iter(["name"]):
        if (process.info.get("name") or "").lower() == LHM_PROCESS:
            return True
    return False


class SensorAppLauncher:
    def __init__(self) -> None:
        if _schtasks("/query", "/tn", HELPER_TASK):
            self.task: str | None = HELPER_TASK
        elif _schtasks("/query", "/tn", LHM_TASK):
            self.task = LHM_TASK
        else:
            self.task = None
        self.available = self.task is not None
        self.shows_tray_icon = self.task == LHM_TASK
        self._started_by_us = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Launch in the background unless it's missing or already running."""
        threading.Thread(target=self._start, daemon=True).start()

    def _start(self) -> None:
        with self._lock:
            if not self.available or self._started_by_us:
                return
            if self.task == HELPER_TASK:
                # The helper stops by itself once this app's single-instance
                # pipe (main.INSTANCE_NAME) is gone.
                if read_helper_output() is not None:
                    # Left over from an earlier run; it now follows this process.
                    self._started_by_us = True
                    return
            elif _lhm_running():
                # The user opened LibreHardwareMonitor; leave it alone on quit too.
                return
            self._started_by_us = _schtasks("/run", "/tn", self.task)

    def restart_if_stopped(self) -> None:
        """Bring the helper back if it stopped while this app is running."""
        if self.task == HELPER_TASK and self._started_by_us and read_helper_output() is None:
            threading.Thread(
                target=lambda: _schtasks("/run", "/tn", HELPER_TASK), daemon=True
            ).start()

    def stop(self) -> None:
        """Close it only if this app started it."""
        with self._lock:
            if self._started_by_us:
                _schtasks("/end", "/tn", self.task)
                self._started_by_us = False
