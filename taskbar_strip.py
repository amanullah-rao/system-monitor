# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import ctypes
import ctypes.wintypes as wintypes
import os
import sys

from PySide6.QtCore import QRect, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QScreen
from PySide6.QtWidgets import QMenu, QWidget

from metrics import CRITICAL, WARNING, Metric, MetricValue, in_order
from system_monitor import SystemReading

try:
    import winreg
except ImportError:  # Not on Windows.
    winreg = None

GWLP_HWNDPARENT = -8  # the owner, for a top-level window
ABM_GETSTATE = 0x4
ABS_AUTOHIDE = 0x1


class _AppBarData(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", wintypes.RECT),
        ("lParam", wintypes.LPARAM),
    ]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _shell32 = ctypes.windll.shell32
    _user32.FindWindowW.restype = ctypes.c_void_p
    _user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    _user32.FindWindowExW.restype = ctypes.c_void_p
    _user32.FindWindowExW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
    ]
    _user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    _user32.MonitorFromWindow.restype = ctypes.c_void_p
    _user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MonitorInfo)]
    _MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )
    _user32.EnumDisplayMonitors.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        _MonitorEnumProc,
        wintypes.LPARAM,
    ]
    _user32.GetForegroundWindow.restype = ctypes.c_void_p
    _user32.IsZoomed.argtypes = [ctypes.c_void_p]
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    _shell32.SHAppBarMessage.restype = ctypes.c_size_t
    _shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(_AppBarData)]


def _monitor_info(monitor) -> _MonitorInfo | None:
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not monitor or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    return info


def list_monitors() -> dict[str, _MonitorInfo]:
    """Each screen's details from Windows, by device name such as \\\\.\\DISPLAY1."""
    if sys.platform != "win32":
        return {}
    monitors = {}

    def collect(monitor, _dc, _rect, _data) -> bool:
        info = _monitor_info(monitor)
        if info is not None:
            monitors[info.szDevice] = info
        return True

    _user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(collect), 0)
    return monitors


def screen_device_name(screen: QScreen, monitors: dict[str, _MonitorInfo]) -> str:
    """Windows' device name for a Qt screen; Qt itself only gives the model name.

    Qt keeps each screen's top-left corner at its physical position, so the
    two are matched by that corner and the physical width.
    """
    area = screen.geometry()
    width = round(area.width() * screen.devicePixelRatio())
    for name, info in monitors.items():
        rect = info.rcMonitor
        if (
            rect.left == area.left()
            and rect.top == area.top()
            and abs(rect.right - rect.left - width) <= 1
        ):
            return name
    return screen.name()


def find_taskbars(monitors: dict[str, _MonitorInfo]) -> dict[str, int]:
    """The taskbar window on each screen that has one, by screen device name."""
    if sys.platform != "win32":
        return {}
    taskbars = {}
    monitor_info_primary = 0x1
    main = _user32.FindWindowW("Shell_TrayWnd", None)
    primary = next(
        (name for name, info in monitors.items() if info.dwFlags & monitor_info_primary),
        None,
    )
    if main and primary:
        taskbars[primary] = main
    secondary = None
    while True:
        secondary = _user32.FindWindowExW(None, secondary, "Shell_SecondaryTrayWnd", None)
        if not secondary:
            break
        monitor_default_to_nearest = 2
        info = _monitor_info(
            _user32.MonitorFromWindow(secondary, monitor_default_to_nearest)
        )
        if info is not None:
            taskbars.setdefault(info.szDevice, secondary)
    return taskbars


# Windows' own desktop and taskbar windows, which cover a screen without being
# a full-screen app.
SHELL_WINDOW_CLASSES = frozenset(
    {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
)


def full_screen_app_on(monitor: wintypes.RECT) -> bool:
    """Whether the active window fills this screen, as games, videos and Parsec do.

    Windows moves its taskbar behind such windows; the strip should go too.
    A maximized window doesn't count: it leaves the taskbar uncovered.
    """
    hwnd = _user32.GetForegroundWindow()
    if not hwnd or _user32.IsZoomed(hwnd) or not _user32.IsWindowVisible(hwnd):
        return False
    process = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process))
    if process.value == os.getpid():
        return False
    class_name = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, class_name, 64)
    if class_name.value in SHELL_WINDOW_CLASSES:
        return False
    window = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(window)):
        return False
    return (
        window.left <= monitor.left
        and window.top <= monitor.top
        and window.right >= monitor.right
        and window.bottom >= monitor.bottom
    )


def taskbar_auto_hides() -> bool:
    data = _AppBarData()
    data.cbSize = ctypes.sizeof(_AppBarData)
    return bool(_shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(data)) & ABS_AUTOHIDE)


def auto_hidden_taskbar_rect(
    screen: QScreen, monitor: wintypes.RECT, taskbar: int
) -> QRect | None:
    """Where an auto-hiding taskbar is now, or None while it's tucked away.

    Hidden, it slides off the screen edge with only a sliver left showing.
    """
    window = wintypes.RECT()
    if not _user32.GetWindowRect(taskbar, ctypes.byref(window)):
        return None
    height = window.bottom - window.top
    top = max(window.top, monitor.top)
    bottom = min(window.bottom, monitor.bottom)
    if height <= 0 or bottom - top < height * 0.9:
        return None
    ratio = screen.devicePixelRatio()
    area = screen.geometry()
    return QRect(
        area.left(),
        area.top() + round((top - monitor.top) / ratio),
        area.width(),
        round((bottom - top) / ratio),
    )


# The gap between the strip and the screen's right edge is saved, so adding
# items grows the strip leftwards, away from the tray icons, and the spot
# carries over to another screen.
GAP_KEY = "taskbar_strip/right_gap"
LEGACY_RIGHT_KEY = "taskbar_strip/right"
LEGACY_POSITION_KEY = "taskbar_strip/x"
# Logical pixels left free at the right of the taskbar for tray icons and the clock.
TRAY_RESERVE = 320
COLUMN_GAP = 14
LABEL_GAP = 5
SIDE_PADDING = 8
DEFAULT_FONT_SIZE = 9.0
# How often to follow the taskbar: often while it slides in and out by itself,
# and often enough otherwise to step aside soon after a full-screen app starts.
TRACK_AUTO_HIDE_MS = 150
TRACK_DOCKED_MS = 500

# Warning colors that stay readable on either taskbar theme.
LEVEL_COLORS = {
    False: {WARNING: "#fbbf24", CRITICAL: "#fb7185"},
    True: {WARNING: "#b45309", CRITICAL: "#dc2626"},
}

# (metrics in the column, label width, value width)
Column = tuple[list[Metric], int, int]


def strip_font(points: float = DEFAULT_FONT_SIZE) -> QFont:
    font = QFont("Segoe UI")
    font.setPointSizeF(points)
    return font


def layout_columns(metrics: list[Metric], rows: int, font_metrics: QFontMetrics) -> list[Column]:
    """Fill columns top to bottom, `rows` items each, sized for their widest value."""
    columns = []
    for start in range(0, len(metrics), rows):
        column = metrics[start : start + rows]
        label_width = max(font_metrics.horizontalAdvance(m.short) for m in column)
        value_width = max(font_metrics.horizontalAdvance(m.sample) for m in column)
        columns.append((column, label_width, value_width))
    return columns


def columns_width(columns: list[Column]) -> int:
    content = sum(label + LABEL_GAP + value for _, label, value in columns)
    content += COLUMN_GAP * max(0, len(columns) - 1)
    return SIDE_PADDING * 2 + content


def paint_columns(
    painter: QPainter,
    height: int,
    columns: list[Column],
    values: dict[str, MetricValue],
    light_theme: bool,
    colored: bool,
    font: QFont,
) -> None:
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    line_height = QFontMetrics(font).height()
    text_color = QColor("#1b1b1b") if light_theme else QColor("#ffffff")
    label_color = QColor(text_color)
    label_color.setAlpha(165)
    level_colors = LEVEL_COLORS[light_theme]
    alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    x = SIDE_PADDING
    for column, label_width, value_width in columns:
        top = (height - len(column) * line_height) / 2
        for row, metric in enumerate(column):
            y = top + row * line_height
            value = values.get(metric.key, MetricValue("--"))
            painter.setPen(label_color)
            painter.drawText(QRectF(x, y, label_width, line_height), alignment, metric.short)
            color = text_color
            if colored and value.level in level_colors:
                color = QColor(level_colors[value.level])
            painter.setPen(color)
            painter.drawText(
                QRectF(x + label_width + LABEL_GAP, y, value_width, line_height),
                alignment,
                value.text,
            )
        x += label_width + LABEL_GAP + value_width + COLUMN_GAP


def taskbar_uses_light_theme() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
            return bool(value)
    except OSError:
        return False


class TaskbarStrip(QWidget):
    """Always-on-top text overlay that sits on the Windows taskbar.

    With two rows, items fill columns top to bottom:  ↑ 12 KB/s   CPU 17%
                                                       ↓ 96 KB/s   RAM 43%
    """

    show_monitor_requested = Signal()
    settings_requested = Signal()
    hide_requested = Signal()
    quit_requested = Signal()

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setToolTip("Drag to move · double-click to open · right-click for options")
        self._settings = QSettings()
        self._light_theme = taskbar_uses_light_theme()
        self._colored = True
        # Whether the user wants the strip; it still hides while an
        # auto-hiding taskbar is tucked away.
        self._enabled = False
        self._screen_name = ""
        self._hide_in_full_screen = True
        self._taskbar: int | None = None
        self._bar = QRect()
        self._drag_offset: float | None = None
        self._keys: list[str] = []
        self._rows = 2
        self._metrics: list[Metric] = []
        self._values: dict[str, MetricValue] = {}
        self._columns: list[Column] = []
        self._font = strip_font()
        self._font_metrics = QFontMetrics(self._font)
        self._migrate_position()

        self._menu = QMenu()
        self._menu.addAction("Open System Monitor").triggered.connect(
            self.show_monitor_requested
        )
        self._menu.addAction("Edit layout…").triggered.connect(self.settings_requested)
        self._menu.addSeparator()
        self._menu.addAction("Move back to default spot").triggered.connect(
            self._reset_position
        )
        self._menu.addAction("Hide from taskbar").triggered.connect(self.hide_requested)
        self._menu.addSeparator()
        self._menu.addAction("Quit System Monitor").triggered.connect(self.quit_requested)

        self._tracker = QTimer(self)
        self._tracker.setInterval(TRACK_DOCKED_MS)
        self._tracker.timeout.connect(self._track_taskbar)
        app = QGuiApplication.instance()
        for screen in QGuiApplication.screens():
            self._watch_screen(screen)
        app.screenAdded.connect(self._watch_screen)
        app.screenAdded.connect(lambda _screen: self._place())
        # Placed on the next pass, once Qt has finished dropping the screen.
        app.screenRemoved.connect(lambda _screen: QTimer.singleShot(0, self._place))
        app.primaryScreenChanged.connect(lambda _screen: self._place())
        self.set_layout(["upload", "download", "cpu", "ram"], 2)

    def _watch_screen(self, screen: QScreen) -> None:
        screen.availableGeometryChanged.connect(lambda _area: self._place())
        screen.geometryChanged.connect(lambda _area: self._place())

    def _migrate_position(self) -> None:
        self._settings.remove(LEGACY_POSITION_KEY)
        right = self._settings.value(LEGACY_RIGHT_KEY)
        if right is None:
            return
        # Earlier versions saved the right edge on the main screen.
        bar = self._docked_rect(QGuiApplication.primaryScreen())
        try:
            self._settings.setValue(GAP_KEY, max(0, bar.right() - int(right)))
        except (TypeError, ValueError):
            pass
        self._settings.remove(LEGACY_RIGHT_KEY)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._tracker.start()
            self._place()
            self._track_taskbar()
        else:
            self._tracker.stop()
            self.hide()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_layout(self, keys: list[str], rows: int) -> None:
        self._keys = keys
        self._rows = max(1, min(2, rows))
        self._metrics = in_order(keys)
        self._columns = layout_columns(self._metrics, self._rows, self._font_metrics)
        self.setFixedWidth(max(40, columns_width(self._columns)))
        self._place()
        self.update()

    def set_colored(self, colored: bool) -> None:
        self._colored = colored
        self.update()

    def set_font_size(self, points: float) -> None:
        self._font = strip_font(points)
        self._font_metrics = QFontMetrics(self._font)
        self.set_layout(self._keys, self._rows)

    def set_hide_in_full_screen(self, hide: bool) -> None:
        self._hide_in_full_screen = hide
        self._place()

    def set_screen(self, name: str) -> None:
        """Sit on the taskbar of the screen with this device name ("" for the main one)."""
        self._screen_name = name
        self._place()
        self._keep_above_taskbar()

    @staticmethod
    def _docked_rect(screen: QScreen) -> QRect:
        full = screen.geometry()
        available = screen.availableGeometry()
        if available.bottom() < full.bottom():
            return QRect(
                full.left(),
                available.bottom() + 1,
                full.width(),
                full.bottom() - available.bottom(),
            )
        if available.top() > full.top():
            return QRect(
                full.left(), full.top(), full.width(), available.top() - full.top()
            )
        # Side taskbar, or none found: fall back to the bottom edge.
        return QRect(full.left(), full.bottom() - 47, full.width(), 48)

    def _locate(self) -> tuple[QScreen, int | None, QRect | None]:
        """The screen, its taskbar window, and the taskbar's area.

        The area is None while an auto-hiding taskbar is tucked away or a
        full-screen app covers the screen. A chosen screen that's gone or has
        no taskbar falls back to the main one.
        """
        monitors = list_monitors()
        taskbars = find_taskbars(monitors)
        primary = QGuiApplication.primaryScreen()
        screens = {
            screen_device_name(screen, monitors): screen
            for screen in QGuiApplication.screens()
        }
        screen = screens.get(self._screen_name, primary)
        device = screen_device_name(screen, monitors)
        if taskbars and device not in taskbars:
            screen = primary
            device = screen_device_name(screen, monitors)
        taskbar = taskbars.get(device)
        monitor = monitors[device].rcMonitor if device in monitors else None
        if (
            self._hide_in_full_screen
            and monitor is not None
            and full_screen_app_on(monitor)
        ):
            return screen, taskbar, None
        if taskbar and monitor is not None and taskbar_auto_hides():
            return screen, taskbar, auto_hidden_taskbar_rect(screen, monitor, taskbar)
        return screen, taskbar, self._docked_rect(screen)

    def _place(self) -> None:
        _screen, self._taskbar, bar = self._locate()
        if bar is None:
            # Taskbar tucked away (auto-hide) or covered by a full-screen app.
            self.hide()
            return
        self._bar = bar
        self.setFixedHeight(bar.height())
        gap = self._settings.value(GAP_KEY, TRAY_RESERVE, type=int)
        self.move(self._clamp_x(bar.right() - gap - self.width() + 1, bar), bar.top())
        if self._enabled and not self.isVisible():
            self.show()

    def _clamp_x(self, x: float, bar: QRect) -> int:
        return int(max(bar.left(), min(x, bar.right() - self.width() + 1)))

    def _reset_position(self) -> None:
        self._settings.remove(GAP_KEY)
        self._place()

    def update_reading(self, reading: SystemReading) -> None:
        self._values = {metric.key: metric.read(reading) for metric in self._metrics}
        self._light_theme = taskbar_uses_light_theme()
        if self.isVisible():
            self.update()

    def _track_taskbar(self) -> None:
        """Follow the taskbar: auto-hide, another screen, or an Explorer restart."""
        if self._drag_offset is not None:
            return
        self._place()
        self._keep_above_taskbar()
        auto_hide = sys.platform == "win32" and taskbar_auto_hides()
        self._tracker.setInterval(TRACK_AUTO_HIDE_MS if auto_hide else TRACK_DOCKED_MS)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Qt resets the native owner while showing, so attach once that's done.
        QTimer.singleShot(0, self._keep_above_taskbar)

    def _keep_above_taskbar(self) -> None:
        """Stay drawn above the taskbar, even while it is active.

        Clicking the taskbar or opening "Show hidden icons" raises the taskbar
        over every other topmost window, and Windows ignores attempts to
        reorder above it while it's active. An owned window, though, always
        stays above its owner, so the strip is made owned by the taskbar. If
        Explorer restarts, the owner is gone and the strip simply survives;
        the next check attaches it to the new taskbar.
        """
        if sys.platform != "win32" or not self.isVisible():
            return
        hwnd = int(self.winId())
        if self._taskbar and _user32.GetWindowLongPtrW(hwnd, GWLP_HWNDPARENT) != self._taskbar:
            _user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, self._taskbar)
        hwnd_topmost = -1
        swp_flags = 0x0001 | 0x0002 | 0x0010  # NOSIZE | NOMOVE | NOACTIVATE
        _user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_flags)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        # A nearly invisible fill keeps the whole strip clickable; fully
        # transparent pixels let mouse events fall through on Windows.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        paint_columns(
            painter,
            self.height(),
            self._columns,
            self._values,
            self._light_theme,
            self._colored,
            self._font,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().x() - self.x()
        elif event.button() == Qt.MouseButton.RightButton:
            self._menu.exec(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is None:
            return
        x = event.globalPosition().x() - self._drag_offset
        self.move(self._clamp_x(x, self._bar), self.y())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            right = self.x() + self.width() - 1
            self._settings.setValue(GAP_KEY, self._bar.right() - right)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_monitor_requested.emit()
