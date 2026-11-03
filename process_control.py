# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Ending a process from the dashboard, with checks so it can't go wrong."""

import os
import subprocess

import psutil

from i18n import tr

# Windows can't run without these; ending one crashes or logs out the PC.
PROTECTED_NAMES = frozenset(
    {
        "system",
        "system idle process",
        "registry",
        "memory compression",
        "secure system",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "services.exe",
        "lsass.exe",
        "winlogon.exe",
        "dwm.exe",
        "fontdrvhost.exe",
    }
)
# Process IDs 0 and 4 are the idle process and the Windows kernel.
LAST_SYSTEM_PID = 4


def protected_reason(pid: int, name: str) -> str | None:
    """Why this process can't be ended from here, or None if it can."""
    if pid == os.getpid():
        return tr("This is System Monitor itself. Use Quit in the tray menu instead.")
    if pid <= LAST_SYSTEM_PID or name.lower() in PROTECTED_NAMES:
        return tr("Windows needs this process to run, so it can't be ended here.")
    return None


def end_process(pid: int, expected_name: str) -> str | None:
    """End a process; returns a problem to show, or None when it worked.

    Windows reuses process IDs, so the name is checked again first: the one
    the user saw may have exited while the question was on screen.
    """
    reason = protected_reason(pid, expected_name)
    if reason:
        return reason
    try:
        process = psutil.Process(pid)
        if process.name().lower() != expected_name.lower():
            return tr("That process has already closed.")
        process.terminate()
        try:
            process.wait(timeout=2)
        except psutil.TimeoutExpired:
            pass
    except psutil.NoSuchProcess:
        return None  # already gone, which is what was asked for
    except psutil.AccessDenied:
        return tr(
            "Windows doesn't allow ending this process. It may belong to the "
            "system or another user."
        )
    except (psutil.Error, OSError) as error:
        return str(error)
    return None


def process_path(pid: int) -> str | None:
    try:
        return psutil.Process(pid).exe() or None
    except (psutil.Error, OSError):
        return None


def show_in_explorer(path: str) -> None:
    """Open the file's folder in Explorer with the file selected."""
    subprocess.Popen(["explorer.exe", f"/select,{path}"])
