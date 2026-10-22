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
# Set once Windows starts signing out or shutting down; nothing in the app
# should start a program after that.
SESSION_ENDING = threading.Event()


def _schtasks(*args: str) -> bool:
    if os.name != "nt" or SESSION_ENDING.is_set():
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


def task_exists(name: str) -> bool:
    """Whether a Task Scheduler task exists, without starting any program.

    Task Scheduler lists tasks in the registry. Their keys are closed to
    standard users, so "access denied" means the task exists and "not
    found" means it doesn't.
    """
    if os.name != "nt":
        return False
    import winreg

    tree = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Schedule\TaskCache\Tree"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"{tree}\{name}"):
            return True
    except PermissionError:
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return _schtasks("/query", "/tn", name)


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


def helper_gpu_temperatures() -> dict[str, float]:
    """GPU core temperatures from the helper, by graphics card name."""
    data = read_helper_output()
    if data is None:
        return {}
    found: dict[str, dict[str, float]] = {}
    for sensor in data.get("temperatures") or []:
        if not isinstance(sensor, dict) or not str(sensor.get("hardware", "")).startswith("Gpu"):
            continue
        try:
            value = float(sensor.get("value"))
        except (TypeError, ValueError):
            continue
        if 0 < value <= 120:
            found.setdefault(str(sensor.get("device", "")), {})[str(sensor.get("name", ""))] = value
    # "GPU Core" is the usual reading; otherwise the hottest one (such as hot spot).
    return {
        device: sensors.get("GPU Core", max(sensors.values()))
        for device, sensors in found.items()
        if device
    }


def _lhm_running() -> bool:
    for process in psutil.process_iter(["name"]):
        if (process.info.get("name") or "").lower() == LHM_PROCESS:
            return True
    return False


class SensorAppLauncher:
    def __init__(self) -> None:
        if task_exists(HELPER_TASK):
            self.task: str | None = HELPER_TASK
        elif task_exists(LHM_TASK):
            self.task = LHM_TASK
        else:
            self.task = None
        self.available = self.task is not None
        self.shows_tray_icon = self.task == LHM_TASK
        self._started_by_us = False
        self._session_ending = False
        self._lock = threading.Lock()

    def session_ending(self) -> None:
        """Windows is signing out or shutting down: start and end nothing from now on.

        Programs launched this late fail with an error dialog (schtasks.exe
        showed one at shutdown), and the helper ends by itself anyway.
        """
        self._session_ending = True
        SESSION_ENDING.set()

    def start(self) -> None:
        """Launch in the background unless it's missing or already running."""
        threading.Thread(target=self._start, daemon=True).start()

    def _start(self) -> None:
        with self._lock:
            if not self.available or self._started_by_us or self._session_ending:
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
        if (
            self.task == HELPER_TASK
            and self._started_by_us
            and not self._session_ending
            and read_helper_output() is None
        ):
            threading.Thread(
                target=lambda: _schtasks("/run", "/tn", HELPER_TASK), daemon=True
            ).start()

    def stop(self, quitting: bool = False) -> None:
        """Close it only if this app started it.

        When the app is quitting, the helper needs no help: it ends by itself
        about a second after this app's pipe closes.
        """
        with self._lock:
            if not self._started_by_us:
                return
            self._started_by_us = False
            if self._session_ending or (quitting and self.task == HELPER_TASK):
                return
            _schtasks("/end", "/tn", self.task)


def pawnio_installed() -> bool:
    """Whether the PawnIO driver, which reading CPU temperature needs, is installed."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\PawnIO"
        ):
            return True
    except OSError:
        return False


def sensor_problem() -> str | None:
    """Why the sensor helper gives no readings, when the reason is known."""
    if not task_exists(HELPER_TASK):
        return (
            "CPU temperature isn't set up. Run the System Monitor installer again "
            "with “Show CPU temperature” ticked."
        )
    if not pawnio_installed():
        return (
            "The PawnIO driver that reading CPU temperature needs isn't installed. "
            "Run the System Monitor installer again (it installs PawnIO with winget), "
            "or install PawnIO from pawnio.eu, then restart the PC."
        )
    if read_helper_output() is None:
        return "The CPU temperature reader isn't running. It's restarted automatically."
    return None
