# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import ctypes
import ctypes.wintypes as wintypes
import os
import sys
from collections import deque
from datetime import date, datetime
from html import escape

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from formatting import (
    format_bytes,
    format_duration,
    format_gb,
    format_rate,
    format_temperature,
)
import dialogs
import process_control
import styles
from restart import start_new_copy
from collectors import DriveReading
from i18n import tr
from metrics import METRICS_BY_KEY
from sampler import SamplerThread
from styles import StyledButton, StyledFrame
from settings import (
    CLOSE_TO_TRAY,
    DATA_LIMIT_GB,
    PROCESS_SORT,
    SPEED_UNIT,
    TEMPERATURE_UNIT,
    AppSettings,
)
from settings_dialog import SettingsDialog
from system_monitor import GpuReading, ProcessReading, SystemReading
import theme
from theme import (
    GLYPH_COMPACT,
    GLYPH_EXPAND,
    GLYPH_SETTINGS,
    glyph_icon,
    level_color,
    level_text,
    make_app_icon,
    match_title_bar,
)

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_KEEP_GEOMETRY = 0x0001 | 0x0002  # NOSIZE | NOMOVE
GW_HWNDNEXT = 2
GWL_EXSTYLE = -20
# Always-on-top (the taskbar, tray flyouts, our strip), click-through, or
# never-focused windows don't count as covering the app window.
IGNORED_EX_STYLES = 0x00000008 | 0x00000020 | 0x08000000
DWMWA_CLOAKED = 14

if sys.platform == "win32":
    _user32 = ctypes.windll.user32
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    _user32.GetTopWindow.restype = ctypes.c_void_p
    _user32.GetTopWindow.argtypes = [ctypes.c_void_p]
    _user32.GetWindow.restype = ctypes.c_void_p
    _user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    _user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.IsIconic.argtypes = [ctypes.c_void_p]
    _user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _dwmapi = ctypes.windll.dwmapi
    _dwmapi.DwmGetWindowAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]


def _covers(hwnd: int, area: wintypes.RECT, own_process: int) -> bool:
    """Whether a window above ours is a visible app window overlapping `area`."""
    if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
        return False
    if _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & IGNORED_EX_STYLES:
        return False
    process = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process))
    if process.value == own_process:  # our own dialogs and strip
        return False
    cloaked = wintypes.DWORD()
    _dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    if cloaked.value:  # hidden by Windows, e.g. on another virtual desktop
        return False
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (
        rect.left < area.right
        and area.left < rect.right
        and rect.top < area.bottom
        and area.top < rect.bottom
    )


FULL_SIZE = (1040, 760)
FULL_MINIMUM_SIZE = (760, 520)
COMPACT_SIZE = (820, 170)


class Sparkline(QWidget):
    """Filled line chart of recent values; a max_value of None scales to the visible peak.

    Colors throughout the dashboard are theme color names, such as "ACCENT",
    looked up when used so that a theme change applies straight away.
    """

    def __init__(
        self,
        color: str,
        max_value: float | None = 100.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        # One minute of history at the default half-second refresh.
        self._values: deque[float] = deque(maxlen=120)
        self._color_name = color
        self._max_value = max_value
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    # While a reading is only being drawn again (after a setting changed),
    # the charts must not take it as a new sample.
    frozen = False

    def add_value(self, value: float) -> None:
        if Sparkline.frozen:
            return
        value = max(0.0, value)
        if self._max_value is not None:
            value = min(self._max_value, value)
        self._values.append(value)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        if len(self._values) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ceiling = (
            self._max_value
            if self._max_value is not None
            else max(max(self._values), 1e-6) * 1.15
        )
        bottom = self.height() - 1
        usable_height = self.height() - 6
        step = self.width() / (self._values.maxlen - 1)
        # Right-align so the newest value is always at the right edge.
        offset = self.width() - step * (len(self._values) - 1)
        points = [
            QPointF(offset + index * step, bottom - value / ceiling * usable_height)
            for index, value in enumerate(self._values)
        ]

        line = QPainterPath(points[0])
        for point in points[1:]:
            line.lineTo(point)
        area = QPainterPath(line)
        area.lineTo(points[-1].x(), bottom)
        area.lineTo(points[0].x(), bottom)
        area.closeSubpath()

        color = QColor(theme.color(self._color_name))
        gradient = QLinearGradient(0, 0, 0, self.height())
        top_color = QColor(color)
        top_color.setAlpha(70)
        bottom_color = QColor(color)
        bottom_color.setAlpha(0)
        gradient.setColorAt(0, top_color)
        gradient.setColorAt(1, bottom_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        if styles.current().chart_glow:
            glow = QColor(color)
            glow.setAlpha(55)
            painter.setPen(QPen(glow, 6))
            painter.drawPath(line)
        painter.setPen(QPen(color, 2))
        painter.drawPath(line)


class RingGauge(QWidget):
    THICKNESS = 9

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value: float | None = None
        self._color = QColor(theme.ACCENT)
        self.setFixedSize(92, 92)

    def set_value(self, value: float | None, color: str) -> None:
        self._value = value
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = self.THICKNESS / 2
        rect = QRectF(half, half, self.width() - self.THICKNESS, self.height() - self.THICKNESS)
        styles.current().paint_ring(
            painter, rect, self.THICKNESS, self._value, self._color, self.devicePixelRatioF()
        )

        font = QFont("Segoe UI")
        font.setPixelSize(20)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(styles.current().ring_text_color())
        text = f"{self._value:.0f}%" if self._value is not None else "—"
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


class UsageBar(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._color_name = color
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, value))
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = styles.current()
        style.paint_track(painter, QRectF(self.rect()), 3, self.devicePixelRatioF())
        if self._value > 0:
            width = max(6.0, self.width() * self._value / 100)
            normal = theme.color(self._color_name)
            style.paint_bar_fill(
                painter, QRectF(0, 0, width, self.height()), level_color(self._value, normal), 3
            )


class UsageBarDelegate(QStyledItemDelegate):
    """Table cell with a small usage bar and the value on the right."""

    TEXT_WIDTH = 52

    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self._color = color

    def paint(self, painter, option, index) -> None:
        background = QStyleOptionViewItem(option)
        self.initStyleOption(background, index)
        background.text = ""
        style = background.widget.style() if background.widget else QApplication.style()
        style.drawControl(
            QStyle.ControlElement.CE_ItemViewItem, background, painter, background.widget
        )

        value = float(index.data(Qt.ItemDataRole.UserRole) or 0.0)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        rect = QRectF(option.rect.adjusted(8, 0, -8, 0))
        bar = QRectF(
            rect.left(),
            rect.center().y() - 3,
            max(0.0, rect.width() - self.TEXT_WIDTH - 8),
            6,
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        # Rows use the plain bar unless the style asks for its own bar drawing.
        active = styles.current() if styles.current().table_bars else styles.get("classic")
        active.paint_track(painter, bar, 3, 1.0)
        if value > 0:
            filled = QRectF(bar)
            filled.setWidth(max(6.0, bar.width() * min(value, 100.0) / 100))
            active.paint_bar_fill(
                painter, filled, level_color(value, theme.color(self._color)), 3
            )
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            QRectF(rect.right() - self.TEXT_WIDTH, rect.top(), self.TEXT_WIDTH, rect.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        painter.restore()


class Card(StyledFrame):
    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__("card", "card", color, parent)
        self._color_name = color
        self._chip_state: tuple[str, str] | None = None
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 14)
        self.body.setSpacing(10)
        self.apply_style()

        header = QHBoxLayout()
        header.setSpacing(8)
        self._dot = dot = QLabel()
        dot.setFixedSize(8, 8)
        title_label = QLabel(title.upper())
        title_label.setObjectName("cardTitle")
        self.chip = QLabel()
        self.chip.setObjectName("chip")
        self.chip.hide()
        header.addWidget(dot)
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(self.chip)
        self.body.addLayout(header)
        Card.apply_theme_colors(self)

    def apply_theme_colors(self) -> None:
        self.apply_style()
        # Some styles mark a card with a colored bar instead of this dot.
        self._dot.setVisible(not styles.current().card_accent_bar)
        self._dot.setStyleSheet(
            f"background: {theme.color(self._color_name)}; border-radius: 4px;"
        )

    def set_chip(self, text: str, color: str) -> None:
        if self._chip_state == (text, color):
            return
        self._chip_state = (text, color)
        tint = QColor(color)
        self.chip.setText(text)
        self.chip.setStyleSheet(
            f"color: {color}; "
            f"background: rgba({tint.red()}, {tint.green()}, {tint.blue()}, 40);"
        )
        self.chip.show()


class GaugeCard(Card):
    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(title, color, parent)
        self._color = color
        row = QHBoxLayout()
        row.setSpacing(16)
        self.gauge = RingGauge()
        details = QVBoxLayout()
        details.setSpacing(4)
        self.primary = QLabel(tr("Waiting for data…"))
        self.primary.setObjectName("primary")
        self.primary.setWordWrap(True)
        self.secondary = QLabel()
        self.secondary.setObjectName("muted")
        self.secondary.setWordWrap(True)
        self.tertiary = QLabel()
        self.tertiary.setObjectName("small")
        self.tertiary.setWordWrap(True)
        details.addStretch(1)
        details.addWidget(self.primary)
        details.addWidget(self.secondary)
        details.addWidget(self.tertiary)
        details.addStretch(1)
        row.addWidget(self.gauge)
        row.addLayout(details, 1)
        self.body.addLayout(row)
        self.body.addStretch(1)
        self.chart = Sparkline(color)
        self.body.addWidget(self.chart)

    def update_gauge(
        self, percent: float | None, primary: str, secondary: str = "", tertiary: str = ""
    ) -> None:
        color = level_color(percent, theme.color(self._color))
        self.gauge.set_value(percent, color)
        self.primary.setText(primary)
        self.secondary.setText(secondary)
        self.secondary.setVisible(bool(secondary))
        self.tertiary.setText(tertiary)
        self.tertiary.setVisible(bool(tertiary))
        self.set_chip(level_text(percent), color)
        if percent is not None:
            self.chart.add_value(percent)


class NetworkCard(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Network"), "VIOLET", parent)
        row = QHBoxLayout()
        row.setSpacing(36)
        self.download = self._add_column(row, "↓  " + tr("Download"))
        self.upload = self._add_column(row, "↑  " + tr("Upload"))
        row.addStretch(1)
        self.body.addLayout(row)
        self.totals = QLabel(tr("Waiting for data…"))
        self.totals.setObjectName("small")
        self.body.addWidget(self.totals)
        self.body.addStretch(1)
        self.chart = Sparkline("VIOLET", max_value=None)
        self.body.addWidget(self.chart)
        self.apply_theme_colors()

    def apply_theme_colors(self) -> None:
        super().apply_theme_colors()
        self.download.setStyleSheet(f"color: {theme.GREEN};")
        self.upload.setStyleSheet(f"color: {theme.ACCENT};")

    @staticmethod
    def _add_column(row: QHBoxLayout, title: str) -> QLabel:
        column = QVBoxLayout()
        column.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("small")
        value = QLabel("—")
        value.setObjectName("bigValue")
        column.addWidget(heading)
        column.addWidget(value)
        row.addLayout(column)
        return value

    def update_network(self, reading: SystemReading) -> None:
        total = reading.network_sent_mbps + reading.network_received_mbps
        self.download.setText(format_rate(reading.network_received_mbps))
        self.upload.setText(format_rate(reading.network_sent_mbps))
        self.totals.setText(
            f"{reading.network_adapter or tr('All adapters')}  ·  "
            + tr("since Windows started")
            + f"  ↓ {format_bytes(reading.network_received_total_bytes)}   "
            f"↑ {format_bytes(reading.network_sent_total_bytes)}"
        )
        active = total >= 0.05
        self.set_chip(
            tr("Active") if active else tr("Idle"), theme.VIOLET if active else theme.MUTED
        )
        self.chart.add_value(total)


class DataBarChart(QWidget):
    """One bar per day for the last 30 days of internet data."""

    LABEL_HEIGHT = 16

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: tuple[tuple[str, int, int], ...] = ()
        self._hover: int | None = None
        self.setMouseTracking(True)
        self.setFixedHeight(104)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_history(self, history: tuple[tuple[str, int, int], ...]) -> None:
        if history != self._history:
            self._history = history
            self.update()

    def _geometry(self) -> tuple[float, float, float]:
        """Bar width, gap and plot height."""
        count = max(1, len(self._history))
        gap = 3.0
        return (self.width() - gap * (count - 1)) / count, gap, self.height() - self.LABEL_HEIGHT - 4

    @staticmethod
    def _day(iso: str) -> str:
        day = date.fromisoformat(iso)
        return f"{day.month}/{day.day}"

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar, gap, plot = self._geometry()
        totals = [received + sent for _, received, sent in self._history]
        peak = max(totals, default=0)
        base = QColor(theme.VIOLET)
        base.setAlpha(150)
        for index, total in enumerate(totals):
            height = plot * total / peak if peak else 0.0
            height = max(height, 2.0 if total else 0.0)
            color = QColor(theme.ACCENT) if index == len(totals) - 1 else QColor(base)
            if index == self._hover:
                color = QColor(theme.TEXT)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            x = index * (bar + gap)
            painter.drawRoundedRect(QRectF(x, 2 + plot - height, bar, height), 2, 2)
        painter.setPen(QColor(theme.BORDER))
        painter.drawLine(0, int(plot + 3), self.width(), int(plot + 3))
        font = QFont("Segoe UI")
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(theme.MUTED))
        label_area = QRectF(0, self.height() - self.LABEL_HEIGHT, self.width(), self.LABEL_HEIGHT)
        if self._history:
            painter.drawText(label_area, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             self._day(self._history[0][0]))
            painter.drawText(label_area, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             tr("Today"))

    def mouseMoveEvent(self, event) -> None:
        bar, gap, _ = self._geometry()
        index = int(event.position().x() // (bar + gap)) if self._history else None
        if index is not None and not 0 <= index < len(self._history):
            index = None
        if index != self._hover:
            self._hover = index
            self.update()
        if index is not None:
            day, received, sent = self._history[index]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{self._day(day)}:  ↓ {format_bytes(received)}  ↑ {format_bytes(sent)}",
                self,
            )

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._hover is not None:
            self._hover = None
            self.update()


class DataUsageCard(Card):
    """Internet data used today and this month, the last 30 days, and the limit."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Internet data"), "VIOLET", parent)
        row = QHBoxLayout()
        row.setSpacing(36)
        self.today = self._add_column(row, tr("Today"))
        self.month = self._add_column(row, tr("This month"))
        row.addStretch(1)
        self.body.addLayout(row)
        self.chart = DataBarChart()
        self.body.addWidget(self.chart)
        self.limit_bar = UsageBar("VIOLET")
        self.limit_text = QLabel()
        self.limit_text.setObjectName("small")
        self.limit_text.setWordWrap(True)
        self.body.addWidget(self.limit_bar)
        self.body.addWidget(self.limit_text)
        self.body.addStretch(1)

    @staticmethod
    def _add_column(row: QHBoxLayout, title: str) -> QLabel:
        column = QVBoxLayout()
        column.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("small")
        value = QLabel("—")
        value.setObjectName("bigValue")
        column.addWidget(heading)
        column.addWidget(value)
        row.addLayout(column)
        return value

    def update_data(self, reading: SystemReading, limit_gb: int) -> None:
        today = reading.data_today_received + reading.data_today_sent
        month = reading.data_month_received + reading.data_month_sent
        self.today.setText(format_bytes(today))
        self.month.setText(format_bytes(month))
        self.chart.set_history(reading.data_history)
        if limit_gb > 0:
            limit = limit_gb * 1024**3
            percent = month / limit * 100
            self.limit_bar.setVisible(True)
            self.limit_bar.set_value(percent)
            self.limit_text.setText(
                tr("{used} of {limit} monthly limit").format(
                    used=format_bytes(month), limit=format_gb(limit_gb)
                )
            )
            color = theme.RED if percent >= 100 else theme.AMBER if percent >= 80 else theme.VIOLET
            self.set_chip(tr("{percent}% of limit").format(percent=f"{percent:.0f}"), color)
        else:
            self.limit_bar.setVisible(False)
            self.limit_text.setText(
                tr("No monthly limit set. You can set one in Settings → Network.")
            )
            self.chip.hide()
            self._chip_state = None

    def apply_theme_colors(self) -> None:
        super().apply_theme_colors()
        self.chart.update()


class DriveRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        top = QHBoxLayout()
        self.name = QLabel()
        self.name.setObjectName("primary")
        self.free = QLabel()
        self.free.setObjectName("muted")
        top.addWidget(self.name, 1)
        top.addWidget(self.free)
        self.bar = UsageBar("PINK")
        self.detail = QLabel()
        self.detail.setObjectName("small")
        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addWidget(self.detail)

    def set_drive(self, drive: DriveReading) -> None:
        mount = drive.mount.rstrip("\\") or drive.mount
        self.name.setText(f"{mount}  {drive.label}" if drive.label else mount)
        self.free.setText(tr("{free} free").format(free=format_gb(drive.free_gb)))
        self.bar.set_value(drive.percent)
        self.detail.setText(
            tr("{used} of {total} used").format(
                used=format_gb(drive.used_gb), total=format_gb(drive.total_gb)
            )
        )


class DrivesCard(Card):
    """Every drive's free space, not just the Windows drive."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Drives"), "PINK", parent)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(12)
        self._rows: list[DriveRow] = []
        self._empty = QLabel(tr("Waiting for data…"))
        self._empty.setObjectName("muted")
        self.body.addWidget(self._empty)
        self.body.addLayout(self._rows_layout)
        self.body.addStretch(1)

    def update_drives(self, drives: tuple[DriveReading, ...]) -> None:
        self._empty.setVisible(not drives)
        self._empty.setText(tr("No drives were found."))
        while len(self._rows) < len(drives):
            row = DriveRow()
            self._rows_layout.addWidget(row)
            self._rows.append(row)
        for index, row in enumerate(self._rows):
            row.setVisible(index < len(drives))
            if index < len(drives):
                row.set_drive(drives[index])
        if drives:
            worst = max(drive.percent for drive in drives)
            self.set_chip(
                tr("{count} drives").format(count=len(drives))
                if len(drives) != 1
                else tr("1 drive"),
                level_color(worst, theme.MUTED),
            )


class GpuRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.name = QLabel()
        self.name.setObjectName("primary")
        self.name.setWordWrap(True)
        self.bar = UsageBar("AMBER")
        self.detail = QLabel()
        self.detail.setObjectName("small")
        self.detail.setWordWrap(True)
        layout.addWidget(self.name)
        layout.addWidget(self.bar)
        layout.addWidget(self.detail)

    def set_gpu(self, gpu: GpuReading) -> None:
        self.name.setText(gpu.name)
        has_load = gpu.utilization is not None
        self.bar.setVisible(has_load)
        if not has_load:
            text = tr("Live usage isn't available for this graphics adapter.")
            if gpu.temperature_c is not None:
                text = f"{format_temperature(gpu.temperature_c)}  ·  {text}"
            self.detail.setText(text)
            self.setToolTip(gpu.error or "")
            return
        self.bar.set_value(gpu.utilization)
        parts = [tr("Load {percent}%").format(percent=f"{gpu.utilization:.0f}")]
        if gpu.memory_used_mb is not None and gpu.memory_total_mb is not None:
            parts.append(
                tr("Memory {used} of {total}").format(
                    used=format_gb(gpu.memory_used_mb / 1024),
                    total=format_gb(gpu.memory_total_mb / 1024),
                )
            )
        if gpu.temperature_c is not None:
            parts.append(format_temperature(gpu.temperature_c))
        self.detail.setText("  ·  ".join(parts))
        self.setToolTip("")


class GpuCard(Card):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Graphics"), "AMBER", parent)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(14)
        self._rows: list[GpuRow] = []
        self._empty = QLabel(tr("Waiting for data…"))
        self._empty.setObjectName("muted")
        self.body.addWidget(self._empty)
        self.body.addLayout(self._rows_layout)
        self.body.addStretch(1)

    def update_gpus(self, gpus: tuple[GpuReading, ...], status: str) -> None:
        self.setToolTip(status)
        self._empty.setVisible(not gpus)
        self._empty.setText(tr("No graphics adapters were reported by Windows."))
        while len(self._rows) < len(gpus):
            row = GpuRow()
            self._rows_layout.addWidget(row)
            self._rows.append(row)
        for index, row in enumerate(self._rows):
            row.setVisible(index < len(gpus))
            if index < len(gpus):
                row.set_gpu(gpus[index])

        loads = [gpu.utilization for gpu in gpus if gpu.utilization is not None]
        if loads:
            peak = max(loads)
            self.set_chip(level_text(peak), level_color(peak, theme.AMBER))
        else:
            count = len(gpus)
            self.set_chip(
                tr("{count} adapters").format(count=count)
                if count != 1
                else tr("1 adapter"),
                theme.MUTED,
            )


class ProcessCard(Card):
    ROW_HEIGHT = 30
    VISIBLE_ROWS = 10
    PID_ROLE = Qt.ItemDataRole.UserRole + 1

    # The window saves the order, so the choice survives a restart.
    sort_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(tr("Top apps & processes"), "GREEN", parent)
        self._sort = "cpu"
        self._update_sort_chip()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels((tr("Name"), tr("CPU"), tr("Memory")))
        self.table.setItemDelegateForColumn(1, UsageBarDelegate("ACCENT", self.table))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setHighlightSections(False)
        header.setSectionsClickable(True)
        header.setToolTip(tr("Click CPU or Memory to sort"))
        header.sectionClicked.connect(self._header_clicked)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 200)
        header.resizeSection(2, 110)
        self.table.horizontalHeaderItem(2).setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.setMinimumHeight(self.ROW_HEIGHT * self.VISIBLE_ROWS + 36)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_menu)
        footnote = QLabel(
            tr("CPU is shown as a share of your processor's total capacity.")
            + "  "
            + tr("Right-click an app for more.")
        )
        footnote.setObjectName("small")
        self.body.addWidget(self.table)
        self.body.addWidget(footnote)

    def _update_sort_chip(self) -> None:
        self.set_chip(
            tr("Sorted by memory") if self._sort == "memory" else tr("Sorted by CPU"),
            theme.ACCENT,
        )

    def set_sort(self, sort: str) -> None:
        self._sort = "memory" if sort == "memory" else "cpu"
        self._update_sort_chip()

    def apply_theme_colors(self) -> None:
        super().apply_theme_colors()
        self._chip_state = None
        self._update_sort_chip()
        self.table.viewport().update()

    def _header_clicked(self, section: int) -> None:
        if section in (1, 2):
            self.sort_requested.emit("cpu" if section == 1 else "memory")

    def _show_menu(self, position) -> None:
        item = self.table.itemAt(position)
        menu = QMenu(self.table)
        if item is not None:
            name_item = self.table.item(item.row(), 0)
            pid = name_item.data(self.PID_ROLE)
            name = name_item.text()
            menu.addAction(tr("End task")).triggered.connect(
                lambda: self._end_task(pid, name)
            )
            menu.addAction(tr("Open file location")).triggered.connect(
                lambda: self._open_location(pid)
            )
            menu.addSeparator()
        menu.addAction(tr("Sort by CPU")).triggered.connect(
            lambda: self.sort_requested.emit("cpu")
        )
        menu.addAction(tr("Sort by memory")).triggered.connect(
            lambda: self.sort_requested.emit("memory")
        )
        menu.exec(self.table.viewport().mapToGlobal(position))

    def _end_task(self, pid: int, name: str) -> None:
        reason = process_control.protected_reason(pid, name)
        if reason:
            dialogs.inform(self, tr("End task"), reason)
            return
        if not dialogs.ask(
            self,
            tr("End task"),
            tr(
                "End {name}? Anything you haven't saved in it will be lost."
            ).format(name=name),
            tr("End task"),
        ):
            return
        problem = process_control.end_process(pid, name)
        if problem:
            dialogs.warn(self, tr("End task"), problem)

    def _open_location(self, pid: int) -> None:
        path = process_control.process_path(pid)
        if path:
            process_control.show_in_explorer(path)
        else:
            dialogs.inform(
                self,
                tr("Open file location"),
                tr("Windows doesn't share where this process is stored."),
            )

    def update_processes(self, processes: tuple[ProcessReading, ...]) -> None:
        self.table.setRowCount(len(processes))
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for row, process in enumerate(processes):
            name = self._cell(row, 0)
            name.setText(process.name)
            name.setData(self.PID_ROLE, process.pid)
            name.setToolTip(
                tr("{name}\nProcess ID: {pid}").format(name=process.name, pid=process.pid)
            )
            cpu = self._cell(row, 1)
            cpu.setText(f"{process.cpu_percent:.1f}%")
            cpu.setData(Qt.ItemDataRole.UserRole, process.cpu_percent)
            memory = self._cell(row, 2)
            memory.setText(format_bytes(process.memory_mb * 1024**2))
            memory.setTextAlignment(right)
            memory.setToolTip(
                tr("{percent}% of installed memory").format(
                    percent=f"{process.memory_percent:.1f}"
                )
            )

    def _cell(self, row: int, column: int) -> QTableWidgetItem:
        item = self.table.item(row, column)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, column, item)
        return item


class CompactIndicator(StyledFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__("compactIndicator", "compact", None, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.apply_style()
        heading = QLabel(title.upper())
        heading.setObjectName("cardTitle")
        self.value = QLabel("—")
        self.value.setObjectName("compactValue")
        self.detail = QLabel()
        self.detail.setObjectName("small")
        layout.addWidget(heading)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_values(self, value: str, detail: str, color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color or theme.TEXT};")
        self.detail.setText(detail)


class MonitorWindow(QMainWindow):
    hidden_to_tray = Signal()

    def __init__(self, sampler: SamplerThread, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings
        self._compact = False
        self._settings_dialog: SettingsDialog | None = None
        self._last_reading: SystemReading | None = None
        # Set by TrayMonitor when a tray icon can keep the app reachable.
        self.tray_available = False
        # Set by main() when LibreHardwareMonitor's launch task exists.
        self.sensor_app_available = False
        self.sensor_app_shows_tray_icon = False
        # Qt's quit() first asks every window to close and cancels if one
        # refuses, so closing to the tray must stand aside while quitting.
        self._quitting = False
        self.setWindowTitle("System Monitor")
        self.setWindowIcon(make_app_icon())
        self.resize(*FULL_SIZE)
        self.setMinimumSize(*FULL_MINIMUM_SIZE)

        self.cpu_card = GaugeCard(tr("Processor"), "ACCENT")
        self.memory_card = GaugeCard(tr("Memory"), "GREEN")
        self.disk_card = GaugeCard(tr("Storage"), "AMBER")
        self.network_card = NetworkCard()
        self.gpu_card = GpuCard()
        self.data_card = DataUsageCard()
        self.drives_card = DrivesCard()
        self.process_card = ProcessCard()
        self.process_card.set_sort(settings.value(PROCESS_SORT))
        self.process_card.sort_requested.connect(
            lambda sort: settings.set_value(PROCESS_SORT, sort)
        )
        settings.changed.connect(self._on_setting_changed)
        self.compact_cpu = CompactIndicator("CPU")
        self.compact_memory = CompactIndicator(tr("Memory"))
        self.compact_gpu = CompactIndicator("GPU")
        self.compact_network = CompactIndicator(tr("Network"))

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(22, 18, 22, 18)
        root_layout.setSpacing(16)
        root_layout.addLayout(self._make_header())

        self.pages = QStackedWidget()
        self.dashboard = self._make_dashboard()
        self.compact_page = self._make_compact_page()
        self.pages.addWidget(self.dashboard)
        self.pages.addWidget(self.compact_page)
        root_layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self._apply_style_spacing()
        sampler.reading_ready.connect(self._show_reading)
        sampler.sample_failed.connect(self._show_error)

    def _apply_style_spacing(self) -> None:
        """Cards leave room for their own shadows in the Soft style, so the
        layout only adds what's left of the usual gap."""
        style = styles.current()
        extra = 2 * style.card_room("card") if style.custom_painting else 0
        self._grid.setSpacing(max(0, 14 - extra))
        self._compact_layout.setSpacing(max(0, 10 - extra))

    def _on_setting_changed(self, key: str) -> None:
        if key == PROCESS_SORT:
            self.process_card.set_sort(self._settings.value(PROCESS_SORT))
        if key in (PROCESS_SORT, DATA_LIMIT_GB, SPEED_UNIT, TEMPERATURE_UNIT):
            self._redraw()

    def _redraw(self) -> None:
        """Show the latest reading again, without adding it to the charts."""
        if self._last_reading is None:
            return
        Sparkline.frozen = True
        try:
            self._show_reading(self._last_reading)
        finally:
            Sparkline.frozen = False

    def _make_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(40, 40))
        title_column = QVBoxLayout()
        title_column.setSpacing(0)
        title = QLabel("System Monitor")
        title.setObjectName("appTitle")
        self.subtitle = QLabel(tr("Starting up…"))
        self.subtitle.setObjectName("muted")
        title_column.addWidget(title)
        title_column.addWidget(self.subtitle)
        layout.addWidget(logo)
        layout.addLayout(title_column)
        layout.addStretch(1)

        self.mode_button = StyledButton(glyph_icon(GLYPH_COMPACT), "  " + tr("Compact view"))
        self.mode_button.setToolTip(tr("Switch to a small window with just the key numbers"))
        self.mode_button.clicked.connect(self._toggle_mode)
        self.settings_button = settings_button = StyledButton(glyph_icon(GLYPH_SETTINGS), "")
        settings_button.setObjectName("iconButton")
        settings_button.setToolTip(tr("Settings"))
        settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.mode_button)
        layout.addWidget(settings_button)
        return layout

    def _make_dashboard(self) -> QScrollArea:
        page = QWidget()
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        self._grid = grid
        grid.addWidget(self.cpu_card, 0, 0)
        grid.addWidget(self.memory_card, 0, 1)
        grid.addWidget(self.disk_card, 0, 2)
        grid.addWidget(self.network_card, 1, 0, 1, 2)
        grid.addWidget(self.gpu_card, 1, 2)
        grid.addWidget(self.data_card, 2, 0, 1, 2)
        grid.addWidget(self.drives_card, 2, 2)
        grid.addWidget(self.process_card, 3, 0, 1, 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(page)
        return scroll_area

    def _make_compact_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        self._compact_layout = layout
        for indicator in (
            self.compact_cpu,
            self.compact_memory,
            self.compact_gpu,
            self.compact_network,
        ):
            layout.addWidget(indicator, 1)
        return page

    @property
    def last_reading(self) -> SystemReading | None:
        return self._last_reading

    def apply_theme_colors(self) -> None:
        """Repaint with the current theme (the stylesheet itself is app-wide)."""
        for card in (
            self.cpu_card,
            self.memory_card,
            self.disk_card,
            self.network_card,
            self.gpu_card,
            self.data_card,
            self.drives_card,
            self.process_card,
        ):
            card.apply_theme_colors()
        self.mode_button.setIcon(
            glyph_icon(GLYPH_EXPAND if self._compact else GLYPH_COMPACT)
        )
        self.settings_button.setIcon(glyph_icon(GLYPH_SETTINGS))
        self._apply_style_spacing()
        styles.refresh_all()
        self._redraw()
        if self._settings_dialog is not None:
            self._settings_dialog.apply_theme_colors()
        match_title_bar(self)
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        match_title_bar(self)

    def paintEvent(self, event) -> None:
        style = styles.current()
        if style.has_backdrop:
            painter = QPainter(self)
            style.paint_backdrop(painter, QRectF(self.rect()), self.devicePixelRatioF())
            painter.end()
        super().paintEvent(event)

    def bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        if sys.platform == "win32":
            # Windows may refuse to hand over focus (it then only flashes the
            # taskbar button), which left the window opening behind others.
            # Lifting it to the top of the z-order works regardless.
            hwnd = int(self.winId())
            for insert_after in (HWND_TOPMOST, HWND_NOTOPMOST):
                _user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, SWP_KEEP_GEOMETRY)
        self.activateWindow()

    def is_in_front(self) -> bool:
        """Whether no other app's window covers any part of this one."""
        if sys.platform != "win32":
            return self.isActiveWindow()
        hwnd = int(self.winId())
        mine = wintypes.RECT()
        _user32.GetWindowRect(hwnd, ctypes.byref(mine))
        own_process = os.getpid()
        current = _user32.GetTopWindow(None)
        while current:
            if current == hwnd:
                return True
            if _covers(current, mine, own_process):
                return False
            current = _user32.GetWindow(current, GW_HWNDNEXT)
        return True

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                self._settings,
                self.tray_available,
                self.sensor_app_available,
                self.sensor_app_shows_tray_icon,
                self,
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _toggle_mode(self) -> None:
        self._compact = not self._compact
        if self._compact:
            self.pages.setCurrentWidget(self.compact_page)
            self.mode_button.setIcon(glyph_icon(GLYPH_EXPAND))
            self.mode_button.setText("  " + tr("Full dashboard"))
            self.setMinimumSize(0, 0)
            self.resize(*COMPACT_SIZE)
        else:
            self.pages.setCurrentWidget(self.dashboard)
            self.mode_button.setIcon(glyph_icon(GLYPH_COMPACT))
            self.mode_button.setText("  " + tr("Compact view"))
            self.setMinimumSize(*FULL_MINIMUM_SIZE)
            self.resize(*FULL_SIZE)

    def allow_quit(self) -> None:
        """Let the next close request end the app (Quit, Windows sign-out or shutdown)."""
        self._quitting = True

    def restart_application(self) -> None:
        """Start a fresh copy, which waits for this one to exit, then quit."""
        if start_new_copy():
            self.quit_application()

    def quit_application(self) -> None:
        self.allow_quit()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if (
            not self._quitting
            and self.tray_available
            and self._settings.value(CLOSE_TO_TRAY)
        ):
            event.ignore()
            self.hide()
            self.hidden_to_tray.emit()
        else:
            event.accept()
            QApplication.quit()

    def _show_error(self, message: str) -> None:
        self.subtitle.setText(
            f'<span style="color:{theme.RED}">●</span>  {escape(message)}'
        )

    def _show_reading(self, reading: SystemReading) -> None:
        self._last_reading = reading
        temperature = format_temperature(reading.cpu_temperature_c, tr("not available ⓘ"))
        self.cpu_card.update_gauge(
            reading.cpu_percent,
            tr("Temperature: {value}").format(value=temperature),
            tr("{count} logical processors").format(count=reading.logical_cpus),
            tr("Running for {duration}").format(
                duration=format_duration(reading.uptime_seconds)
            ),
        )
        self.cpu_card.primary.setToolTip(reading.cpu_temperature_status)

        self.memory_card.update_gauge(
            reading.memory_percent,
            tr("{used} of {total} used").format(
                used=format_gb(reading.memory_used_gb),
                total=format_gb(reading.memory_total_gb),
            ),
            tr("{free} available").format(free=format_gb(reading.memory_available_gb)),
        )

        if reading.disk_percent is None:
            self.disk_card.update_gauge(
                None,
                tr("Drive {drive}").format(drive=reading.disk_name),
                tr("Couldn't read this drive"),
            )
        else:
            self.disk_card.update_gauge(
                reading.disk_percent,
                tr("{used} of {total} used").format(
                    used=format_gb(reading.disk_used_gb),
                    total=format_gb(reading.disk_total_gb),
                ),
                tr("{free} free on {drive}").format(
                    free=format_gb(reading.disk_free_gb), drive=reading.disk_name
                ),
                self._disk_activity_text(reading),
            )

        self.network_card.update_network(reading)
        self.data_card.update_data(reading, self._settings.value(DATA_LIMIT_GB))
        self.drives_card.update_drives(reading.drives)
        self.gpu_card.update_gpus(reading.gpus, reading.gpu_status)
        by_memory = self._settings.value(PROCESS_SORT) == "memory"
        self.process_card.update_processes(
            reading.processes_by_memory if by_memory else reading.processes
        )

        gpu_loads = [
            gpu.utilization for gpu in reading.gpus if gpu.utilization is not None
        ]
        gpu_load = sum(gpu_loads) / len(gpu_loads) if gpu_loads else None
        self.compact_cpu.set_values(
            f"{reading.cpu_percent:.0f}%",
            format_temperature(reading.cpu_temperature_c, tr("Temp not available")),
            level_color(reading.cpu_percent, theme.TEXT),
        )
        self.compact_memory.set_values(
            f"{reading.memory_percent:.0f}%",
            tr("{used} of {total}").format(
                used=format_gb(reading.memory_used_gb),
                total=format_gb(reading.memory_total_gb),
            ),
            level_color(reading.memory_percent, theme.TEXT),
        )
        self.compact_gpu.set_values(
            f"{gpu_load:.0f}%" if gpu_load is not None else "N/A",
            tr("{count} adapter(s)").format(count=len(reading.gpus))
            if reading.gpus
            else tr("No adapters"),
            level_color(gpu_load, theme.TEXT) if gpu_load is not None else theme.MUTED,
        )
        self.compact_network.set_values(
            f"↓ {format_rate(reading.network_received_mbps)}",
            f"↑ {format_rate(reading.network_sent_mbps)}",
        )

        updated = datetime.fromtimestamp(reading.timestamp).strftime("%H:%M:%S")
        battery = ""
        if reading.battery_percent is not None:
            state = tr("charging") if reading.battery_plugged else tr("on battery")
            extra = METRICS_BY_KEY["battery_info"].read(reading).text
            detail = f", {extra}" if extra != "N/A" else ""
            battery = "  ·  " + tr("Battery {percent}% ({state})").format(
                percent=f"{reading.battery_percent:.0f}", state=state + detail
            )
        self.subtitle.setText(
            f'<span style="color:{theme.GREEN}">●</span>  '
            + tr("Live  ·  updated {time}").format(time=updated)
            + battery
        )

    @staticmethod
    def _disk_activity_text(reading: SystemReading) -> str:
        if reading.disk_read_bytes_per_s is None or reading.disk_write_bytes_per_s is None:
            return ""
        return tr("Read {read}/s  ·  Write {write}/s").format(
            read=format_bytes(reading.disk_read_bytes_per_s),
            write=format_bytes(reading.disk_write_bytes_per_s),
        )
