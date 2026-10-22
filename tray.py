# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import time

from PySide6.QtCore import QObject, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from alerts import UsageAlerts
from formatting import (
    format_bytes,
    format_duration,
    format_gb,
    format_rate,
    format_temperature,
)
from metrics import (
    CRITICAL,
    METRICS,
    METRICS_BY_KEY,
    TRAY_ICON_CHOICES,
    WARNING,
    Metric,
    MetricValue,
    in_order,
)
from sampler import SamplerThread
from settings import (
    ALERTS_ENABLED,
    STRIP_COLORED,
    STRIP_FONT_SIZE,
    STRIP_HIDE_FULL_SCREEN,
    STRIP_ITEMS,
    STRIP_ROWS,
    STRIP_SCREEN,
    STRIP_VISIBLE,
    TRAY_ICON,
    AppSettings,
)
from system_monitor import SystemReading
from taskbar_strip import TaskbarStrip
# Tray icons sit on the taskbar, so they keep the dark theme's colors
# (imported once) whatever theme the app windows use.
from theme import AMBER, MUTED, RED, SURFACE, TRACK, make_app_icon
from widgets import MonitorWindow

ICON_SIZE = 64
# Windows cuts tray tooltips off at 127 characters.
TOOLTIP_LIMIT = 127


def make_tray_icon(metric: Metric, value: MetricValue | None) -> QIcon:
    """Number in the metric's color inside a colored frame, with a fill bar."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    accent = QColor(metric.accent)
    painter.setPen(QPen(accent, 4))
    painter.setBrush(QColor(SURFACE))
    painter.drawRoundedRect(QRectF(2, 2, ICON_SIZE - 4, ICON_SIZE - 4), 12, 12)

    number = value.number if value is not None else None
    if value is None:
        text, color = metric.short[0], QColor(MUTED)
    elif number is None:
        text, color = "–", QColor(MUTED)
    else:
        text = f"{min(number, 999):.0f}"
        color = {CRITICAL: QColor(RED), WARNING: QColor(AMBER)}.get(value.level, accent)

    font = QFont("Segoe UI")
    font.setBold(True)
    font.setPixelSize(28 if len(text) >= 3 else 38)
    painter.setFont(font)
    painter.setPen(color)
    painter.drawText(
        QRectF(0, -3, ICON_SIZE, ICON_SIZE - 10), Qt.AlignmentFlag.AlignCenter, text
    )

    if number is not None:
        track = QRectF(10, ICON_SIZE - 15, ICON_SIZE - 20, 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TRACK))
        painter.drawRoundedRect(track, 3, 3)
        filled = QRectF(track)
        filled.setWidth(track.width() * max(0.0, min(100.0, number)) / 100)
        painter.setBrush(color)
        painter.drawRoundedRect(filled, 3, 3)

    painter.end()
    return QIcon(pixmap)


def build_tooltip(reading: SystemReading) -> str:
    """Most useful lines first, stopping before Windows would cut the text off."""
    lines = [
        f"CPU {reading.cpu_percent:.0f}% · "
        f"{format_temperature(reading.cpu_temperature_c, 'temp N/A')}",
        f"RAM {reading.memory_percent:.0f}% · "
        f"{format_gb(reading.memory_used_gb)} of {format_gb(reading.memory_total_gb)}",
        f"↓ {format_rate(reading.network_received_mbps)}  "
        f"↑ {format_rate(reading.network_sent_mbps)}",
        "Data today "
        f"{format_bytes(reading.data_today_received + reading.data_today_sent)}",
    ]
    gpu_parts = [
        value.text
        for value in (
            METRICS_BY_KEY["gpu"].read(reading),
            METRICS_BY_KEY["gpu_temp"].read(reading),
        )
        if value.number is not None
    ]
    if gpu_parts:
        lines.append("GPU " + " · ".join(gpu_parts))
    if reading.disk_percent is not None and reading.disk_free_gb is not None:
        lines.append(f"{reading.disk_name} {format_gb(reading.disk_free_gb)} free")
    if reading.battery_percent is not None:
        lines.append(f"Battery {METRICS_BY_KEY['battery'].read(reading).text}")
    if reading.processes:
        top = reading.processes[0]
        lines.append(f"Top: {top.name} {top.cpu_percent:.0f}%")
    lines.append(f"Up {format_duration(reading.uptime_seconds)}")

    tooltip = ""
    for line in lines:
        candidate = f"{tooltip}\n{line}" if tooltip else line
        if len(candidate) > TOOLTIP_LIMIT:
            break
        tooltip = candidate
    return tooltip


class TrayMonitor(QObject):
    """Live readings in the Windows notification area and on the taskbar."""

    def __init__(
        self, window: MonitorWindow, sampler: SamplerThread, settings: AppSettings
    ) -> None:
        super().__init__(window)
        self._window = window
        self._settings = settings
        self._told_about_tray = False
        self._last_toggle = 0.0
        self._last_reading: SystemReading | None = None
        # Last drawn (choice, text, level), so an unchanged icon isn't redrawn.
        self._drawn: tuple[str, str, int] | None = None
        self._alerts = UsageAlerts(self)
        self._alerts.alert.connect(self._notify)

        self._menu = QMenu()
        open_action = self._menu.addAction("Open System Monitor")
        bold = open_action.font()
        bold.setBold(True)
        open_action.setFont(bold)
        open_action.triggered.connect(window.bring_to_front)
        self._menu.addSeparator()

        icon_menu = self._menu.addMenu("Tray icon shows")
        icon_choices = QActionGroup(icon_menu)
        self._icon_actions: dict[str, QAction] = {}
        for key, label in TRAY_ICON_CHOICES:
            action = icon_menu.addAction(label)
            action.setCheckable(True)
            icon_choices.addAction(action)
            action.triggered.connect(
                lambda _=False, key=key: self._settings.set_value(TRAY_ICON, key)
            )
            self._icon_actions[key] = action
        strip_menu = self._menu.addMenu("Taskbar strip")
        self._strip_action = self._add_toggle(strip_menu, "Show on taskbar", STRIP_VISIBLE)
        self._colored_action = self._add_toggle(
            strip_menu, "Color warnings", STRIP_COLORED
        )
        strip_menu.addAction("Edit layout and order…").triggered.connect(
            window.open_settings
        )
        strip_menu.addSeparator()
        self._strip_item_actions = {
            metric.key: self._add_list_toggle(strip_menu, metric.name, STRIP_ITEMS, metric.key)
            for metric in METRICS
        }
        self._alerts_action = self._add_toggle(self._menu, "Usage alerts", ALERTS_ENABLED)
        self._menu.addSeparator()
        self._menu.addAction("Settings…").triggered.connect(window.open_settings)
        self._menu.addAction("Quit System Monitor").triggered.connect(
            window.quit_application
        )

        self._strip = TaskbarStrip()
        self._strip.show_monitor_requested.connect(window.bring_to_front)
        self._strip.settings_requested.connect(window.open_settings)
        self._strip.quit_requested.connect(window.quit_application)
        self._strip.hide_requested.connect(
            lambda: self._settings.set_value(STRIP_VISIBLE, False)
        )

        # One icon only, so the notification area holds a single entry for the app.
        self._icon = QSystemTrayIcon(make_app_icon(), self)
        self._icon.setToolTip("System Monitor · starting…")
        self._icon.setContextMenu(self._menu)
        self._icon.activated.connect(self._on_activated)
        self._icon.show()

        settings.changed.connect(self._apply_setting)
        for key in (
            TRAY_ICON,
            STRIP_FONT_SIZE,
            STRIP_SCREEN,
            STRIP_HIDE_FULL_SCREEN,
            STRIP_ITEMS,
            STRIP_COLORED,
            STRIP_VISIBLE,
            ALERTS_ENABLED,
        ):
            self._apply_setting(key)

        window.tray_available = True
        window.hidden_to_tray.connect(self._on_hidden_to_tray)
        sampler.reading_ready.connect(self._show_reading)

    def _add_toggle(self, menu: QMenu, text: str, key: str) -> QAction:
        action = menu.addAction(text)
        action.setCheckable(True)
        action.toggled.connect(lambda checked: self._settings.set_value(key, checked))
        return action

    def _add_list_toggle(self, menu: QMenu, text: str, key: str, item: str) -> QAction:
        action = menu.addAction(text)
        action.setCheckable(True)
        action.toggled.connect(
            lambda checked: self._toggle_list_item(key, item, checked)
        )
        return action

    def _toggle_list_item(self, key: str, item: str, checked: bool) -> None:
        if not self._settings.toggle_key(key, item, checked):
            # The last item can't be removed; put the check mark back.
            self._apply_setting(key)

    @staticmethod
    def _set_checked(action: QAction, checked: bool) -> None:
        action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(False)

    def _icon_choice(self) -> str:
        choice = self._settings.value(TRAY_ICON)
        return choice if choice in self._icon_actions else "logo"

    def _apply_setting(self, key: str) -> None:
        if key == TRAY_ICON:
            self._set_checked(self._icon_actions[self._icon_choice()], True)
            self._drawn = None
            if self._icon_choice() == "logo":
                self._icon.setIcon(make_app_icon())
        elif key == STRIP_VISIBLE:
            visible = self._settings.value(STRIP_VISIBLE)
            self._set_checked(self._strip_action, visible)
            self._strip.set_enabled(visible)
        elif key in (STRIP_ITEMS, STRIP_ROWS):
            selected = in_order(self._settings.keys(STRIP_ITEMS)) or [
                METRICS_BY_KEY["cpu"]
            ]
            for metric in METRICS:
                self._set_checked(
                    self._strip_item_actions[metric.key], metric in selected
                )
            self._strip.set_layout(
                [metric.key for metric in selected], self._settings.value(STRIP_ROWS)
            )
        elif key == STRIP_FONT_SIZE:
            self._strip.set_font_size(self._settings.value(STRIP_FONT_SIZE))
        elif key == STRIP_HIDE_FULL_SCREEN:
            self._strip.set_hide_in_full_screen(self._settings.value(STRIP_HIDE_FULL_SCREEN))
        elif key == STRIP_SCREEN:
            self._strip.set_screen(self._settings.value(STRIP_SCREEN))
        elif key == STRIP_COLORED:
            colored = self._settings.value(STRIP_COLORED)
            self._set_checked(self._colored_action, colored)
            self._strip.set_colored(colored)
        elif key == ALERTS_ENABLED:
            self._set_checked(self._alerts_action, self._settings.value(ALERTS_ENABLED))
        else:
            return
        if self._last_reading is not None:
            self._show_reading(self._last_reading)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            return
        # Windows reports a double-click as a click followed by a double-click;
        # toggling on both hid the window and then brought it straight back.
        now = time.monotonic()
        if now - self._last_toggle < QApplication.doubleClickInterval() / 1000:
            return
        self._last_toggle = now
        window = self._window
        if window.isVisible() and not window.isMinimized() and window.is_in_front():
            window.hide()
        else:
            # Hidden, minimized, or covered by another app: show it in front.
            window.bring_to_front()

    def _notify(self, title: str, message: str) -> None:
        self._icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Warning, 8000)

    def _on_hidden_to_tray(self) -> None:
        if self._told_about_tray:
            return
        self._told_about_tray = True
        self._icon.showMessage(
            "System Monitor is still running",
            "Click the tray icon to open it again, or right-click it for options.",
            QSystemTrayIcon.MessageIcon.Information,
            4000,
        )

    def _show_reading(self, reading: SystemReading) -> None:
        self._last_reading = reading
        choice = self._icon_choice()
        if choice != "logo":
            metric = METRICS_BY_KEY[choice]
            value = metric.read(reading)
            if self._drawn != (choice, value.text, value.level):
                self._drawn = (choice, value.text, value.level)
                self._icon.setIcon(make_tray_icon(metric, value))
        self._icon.setToolTip(build_tooltip(reading))
        if self._strip.is_enabled():
            self._strip.update_reading(reading)
        if self._settings.value(ALERTS_ENABLED):
            self._alerts.check(reading)
