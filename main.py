# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import ctypes
import sys

from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app_info
from sampler import SamplerThread
from sensor_app import SensorAppLauncher
from settings import (
    AUTOSTART_FLAG,
    MANAGE_SENSOR_APP,
    NETWORK_ADAPTER,
    REFRESH_SECONDS,
    START_MINIMIZED,
    THEME,
    AppSettings,
    refresh_autostart_command,
)
from theme import MATCH_WINDOWS, apply_theme, make_app_icon
from tray import TrayMonitor
from widgets import MonitorWindow

INSTANCE_NAME = "LocalSystemTools.SystemMonitor"


def notify_running_instance() -> bool:
    """Ask an already running copy to show its window; True if one answered."""
    if sys.platform == "win32":
        # Let the running copy take focus; otherwise Windows only flashes its
        # taskbar button, and a flashing taskbar covers the taskbar strip.
        asfw_any = -1
        ctypes.windll.user32.AllowSetForegroundWindow(asfw_any)
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def listen_for_other_instances(window: MonitorWindow) -> QLocalServer:
    server = QLocalServer(window)

    def on_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.disconnected.connect(connection.deleteLater)
        window.bring_to_front()

    server.newConnection.connect(on_connection)
    QLocalServer.removeServer(INSTANCE_NAME)
    server.listen(INSTANCE_NAME)
    return server


def main() -> int:
    if sys.platform == "win32":
        # Use our own taskbar identity and icon rather than Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(INSTANCE_NAME)

    app = QApplication(sys.argv)
    app.setApplicationName(app_info.APP_NAME)
    app.setApplicationVersion(app_info.VERSION)
    # Kept as is: QSettings stores preferences under this name, so changing it
    # would reset everyone's settings.
    app.setOrganizationName("Local System Tools")
    app.setWindowIcon(make_app_icon())
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)

    if notify_running_instance():
        return 0

    settings = AppSettings()
    apply_theme(app, settings.value(THEME))
    refresh_autostart_command()

    sensor_app = SensorAppLauncher()
    if settings.value(MANAGE_SENSOR_APP):
        sensor_app.start()

    sampler = SamplerThread(
        settings.value(REFRESH_SECONDS), settings.value(NETWORK_ADAPTER)
    )

    def on_setting_changed(key: str) -> None:
        if key == REFRESH_SECONDS:
            sampler.set_interval(settings.value(key))
        elif key == NETWORK_ADAPTER:
            sampler.set_network_adapter(settings.value(key))
        elif key == THEME:
            switch_theme()
        elif key == MANAGE_SENSOR_APP:
            if settings.value(key):
                sensor_app.start()
            else:
                sensor_app.stop()

    settings.changed.connect(on_setting_changed)

    # Restart the sensor helper if it stops for any reason while the app runs.
    sensor_watchdog = QTimer()
    sensor_watchdog.setInterval(30_000)
    sensor_watchdog.timeout.connect(
        lambda: settings.value(MANAGE_SENSOR_APP) and sensor_app.restart_if_stopped()
    )
    sensor_watchdog.start()

    window = MonitorWindow(sampler, settings)

    def switch_theme() -> None:
        apply_theme(app, settings.value(THEME))
        window.apply_theme_colors()

    # With "Match Windows", follow Windows when its app mode changes.
    app.styleHints().colorSchemeChanged.connect(
        lambda _scheme: settings.value(THEME) == MATCH_WINDOWS and switch_theme()
    )
    window.sensor_app_available = sensor_app.available
    window.sensor_app_shows_tray_icon = sensor_app.shows_tray_icon
    has_tray = QSystemTrayIcon.isSystemTrayAvailable()
    if has_tray:
        TrayMonitor(window, sampler, settings)
    listen_for_other_instances(window)
    def on_session_ending(_manager) -> None:
        # Windows is signing out or shutting down. Close-to-tray must not
        # block it, and no program may be started from now on (schtasks
        # showed an error dialog at shutdown).
        sensor_watchdog.stop()
        sensor_app.session_ending()
        window.allow_quit()

    app.commitDataRequest.connect(on_session_ending)
    app.aboutToQuit.connect(sampler.stop)
    app.aboutToQuit.connect(lambda: sensor_app.stop(quitting=True))

    started_by_windows = AUTOSTART_FLAG in sys.argv[1:]
    if not (has_tray and started_by_windows and settings.value(START_MINIMIZED)):
        window.show()
    sampler.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
