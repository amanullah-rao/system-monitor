# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Restarting the app, for changes that apply at start-up such as the language."""

import sys
from pathlib import Path

from PySide6.QtCore import QProcess

# Tells the new copy to wait until this one has gone, because only one copy
# may run (and the old one still holds the single-instance pipe for a moment).
RESTART_FLAG = "--restarted"


def start_new_copy() -> bool:
    """Start another copy of the app; the caller then quits this one."""
    if getattr(sys, "frozen", False):
        program, arguments = sys.executable, [RESTART_FLAG]
    else:
        script = str(Path(__file__).resolve().with_name("main.py"))
        program, arguments = sys.executable, [script, RESTART_FLAG]
    return QProcess.startDetached(program, arguments)
