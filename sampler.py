# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import threading
import time

from PySide6.QtCore import QThread, Signal

from system_monitor import SystemMonitor


class SamplerThread(QThread):
    """Collect system readings off the GUI thread so the window stays responsive."""

    reading_ready = Signal(object)
    sample_failed = Signal(str)

    def __init__(
        self, interval_seconds: float = 0.5, network_adapter: str = "", parent=None
    ) -> None:
        super().__init__(parent)
        self._interval = interval_seconds
        self._network_adapter = network_adapter
        self._stop_event = threading.Event()

    def run(self) -> None:
        # SystemMonitor runs PowerShell during setup, so build it here rather
        # than delaying the window from appearing.
        try:
            monitor = SystemMonitor()
        except Exception as error:
            self.sample_failed.emit(f"Monitor setup failed: {error}")
            return

        try:
            # Wait one interval before the first sample so CPU percentages
            # have a baseline to compare against. Deadlines advance by a fixed
            # step so the time spent sampling doesn't stretch the interval.
            next_due = time.monotonic() + self._interval
            while not self._stop_event.wait(max(0.0, next_due - time.monotonic())):
                monitor.network_adapter = self._network_adapter
                try:
                    reading = monitor.sample()
                except Exception as error:
                    self.sample_failed.emit(f"Sampling failed: {error}")
                else:
                    self.reading_ready.emit(reading)
                next_due += self._interval
                if next_due < time.monotonic():
                    # Fell behind (e.g. after sleep); don't fire a burst to catch up.
                    next_due = time.monotonic() + self._interval
        finally:
            monitor.close()

    def set_interval(self, seconds: float) -> None:
        # Takes effect after the current wait finishes.
        self._interval = seconds

    def set_network_adapter(self, name: str) -> None:
        """Measure one adapter by name, or all of them with an empty name."""
        self._network_adapter = name

    def stop(self) -> None:
        self._stop_event.set()
        self.wait()
