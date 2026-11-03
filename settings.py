# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

try:
    import winreg
except ImportError:  # Not on Windows.
    winreg = None

STRIP_VISIBLE = "taskbar_strip/visible"
STRIP_ITEMS = "taskbar_strip/items"
STRIP_COLORED = "taskbar_strip/colored"
STRIP_ROWS = "taskbar_strip/rows"
STRIP_FONT_SIZE = "taskbar_strip/font_size"
STRIP_HIDE_FULL_SCREEN = "taskbar_strip/hide_in_full_screen"
# Screen device name (such as DISPLAY2), or empty for the main screen.
STRIP_SCREEN = "taskbar_strip/screen"
# Adapter name as Windows shows it (such as Wi-Fi), or empty for all.
NETWORK_ADAPTER = "network/adapter"
MANAGE_SENSOR_APP = "sensors/manage_lhm"
# "logo" or one metric key from metrics.TRAY_METRICS.
TRAY_ICON = "tray/icon"
CLOSE_TO_TRAY = "window/close_to_tray"
START_MINIMIZED = "startup/minimized"
REFRESH_SECONDS = "sampling/interval_seconds"
ALERTS_ENABLED = "alerts/enabled"
# "dark", "light", or "system" to match Windows (see theme.THEME_CHOICES).
THEME = "appearance/theme"
# "en" or "ko"; takes effect when the app starts (see i18n.LANGUAGES).
LANGUAGE = "appearance/language"
# "classic" or "soft" (see theme.STYLE_CHOICES).
STYLE = "appearance/style"
# "C" or "F".
TEMPERATURE_UNIT = "appearance/temperature_unit"
# "bytes" (KB/s, MB/s) or "bits" (Kbps, Mbps).
SPEED_UNIT = "network/speed_unit"
# Monthly internet data limit in GB; 0 for none. DATA_LIMIT_NOTICE remembers
# the last warning, such as "2026-11:80", so it isn't repeated.
DATA_LIMIT_GB = "network/data_limit_gb"
DATA_LIMIT_NOTICE = "network/data_limit_notice"
# When to alert: percent, and (for drives and the battery) percent left.
ALERT_CPU_PERCENT = "alerts/cpu_percent"
ALERT_RAM_PERCENT = "alerts/ram_percent"
ALERT_DRIVE_FREE_PERCENT = "alerts/drive_free_percent"
ALERT_BATTERY_PERCENT = "alerts/battery_percent"
# Taskbar strip looks.
STRIP_HOVER_PANEL = "taskbar_strip/hover_panel"
STRIP_FONT_FAMILY = "taskbar_strip/font_family"
# Background behind the text, 0 (none) to 100 percent.
STRIP_BACKGROUND_OPACITY = "taskbar_strip/background_opacity"
# Per-item text colors as "cpu=#ff8800,ram=#00ccff".
STRIP_COLORS = "taskbar_strip/colors"
# Dashboard process list order: "cpu" or "memory".
PROCESS_SORT = "dashboard/process_sort"
FIRST_RUN_DONE = "app/first_run_done"

# Earlier settings for several tray icons; replaced by the single TRAY_ICON.
LEGACY_TRAY_KEYS = ("tray/show_memory_icon", "tray/icons")

DEFAULTS: dict[str, bool | int | float | str] = {
    STRIP_VISIBLE: True,
    STRIP_ITEMS: "upload,download,cpu,ram",
    STRIP_COLORED: True,
    STRIP_ROWS: 2,
    STRIP_FONT_SIZE: 9.0,
    STRIP_HIDE_FULL_SCREEN: True,
    STRIP_SCREEN: "",
    NETWORK_ADAPTER: "",
    MANAGE_SENSOR_APP: True,
    TRAY_ICON: "logo",
    CLOSE_TO_TRAY: True,
    START_MINIMIZED: True,
    REFRESH_SECONDS: 0.5,
    ALERTS_ENABLED: True,
    THEME: "dark",
    LANGUAGE: "en",
    STYLE: "classic",
    TEMPERATURE_UNIT: "C",
    SPEED_UNIT: "bytes",
    DATA_LIMIT_GB: 0,
    DATA_LIMIT_NOTICE: "",
    ALERT_CPU_PERCENT: 90,
    ALERT_RAM_PERCENT: 90,
    ALERT_DRIVE_FREE_PERCENT: 10,
    ALERT_BATTERY_PERCENT: 15,
    STRIP_HOVER_PANEL: True,
    STRIP_FONT_FAMILY: "Segoe UI",
    STRIP_BACKGROUND_OPACITY: 0,
    STRIP_COLORS: "",
    PROCESS_SORT: "cpu",
    FIRST_RUN_DONE: False,
}

AUTOSTART_FLAG = "--autostart"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "SystemMonitor"


class AppSettings(QObject):
    """User preferences stored with QSettings; emits the key whenever one changes."""

    changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = QSettings()
        for key in LEGACY_TRAY_KEYS:
            self._store.remove(key)
        # Earlier versions had no welcome page: anyone who already has saved
        # settings is an existing user and doesn't need it.
        if not self._store.contains(FIRST_RUN_DONE) and self._store.allKeys():
            self._store.setValue(FIRST_RUN_DONE, True)

    def value(self, key: str):
        default = DEFAULTS[key]
        return self._store.value(key, default, type=type(default))

    def colors(self) -> dict[str, str]:
        """The per-item strip colors, by metric key."""
        found = {}
        for part in self.value(STRIP_COLORS).split(","):
            key, _, color = part.partition("=")
            if key and color.startswith("#") and len(color) == 7:
                found[key] = color
        return found

    def set_colors(self, colors: dict[str, str]) -> None:
        self.set_value(STRIP_COLORS, ",".join(f"{k}={v}" for k, v in colors.items()))

    def set_value(self, key: str, value) -> None:
        if self.value(key) == value:
            return
        self._store.setValue(key, value)
        self.changed.emit(key)

    # Lists are stored as comma-separated text, which round-trips reliably
    # through the Windows registry.
    def keys(self, key: str) -> list[str]:
        return [part for part in self.value(key).split(",") if part]

    def set_keys(self, key: str, keys: list[str]) -> None:
        self.set_value(key, ",".join(keys))

    def toggle_key(self, key: str, item: str, enabled: bool) -> bool:
        """Add or remove one item; refuses to remove the last one. Returns success."""
        keys = self.keys(key)
        if enabled and item not in keys:
            keys.append(item)
        elif not enabled and item in keys:
            if len(keys) == 1:
                return False
            keys.remove(item)
        self.set_keys(key, keys)
        return True


def autostart_supported() -> bool:
    return winreg is not None


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {AUTOSTART_FLAG}'
    # pythonw.exe runs the app without opening a console window.
    executable = Path(sys.executable)
    windowless = executable.with_name("pythonw.exe")
    if windowless.exists():
        executable = windowless
    script = Path(__file__).resolve().with_name("main.py")
    return f'"{executable}" "{script}" {AUTOSTART_FLAG}'


def _registered_command() -> str | None:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return str(value)
    except OSError:
        return None


def is_autostart_enabled() -> bool:
    return _registered_command() is not None


def set_autostart(enabled: bool) -> None:
    """Add or remove the sign-in entry; raises OSError if the registry refuses."""
    if winreg is None:
        raise OSError("Starting with Windows is only available on Windows")
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def refresh_autostart_command() -> None:
    """Keep the sign-in entry pointing here if the app folder or Python moved."""
    registered = _registered_command()
    if registered is not None and registered != autostart_command():
        try:
            set_autostart(True)
        except OSError:
            pass
