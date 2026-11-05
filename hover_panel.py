# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""The details panel that opens above the taskbar strip while the mouse is on it."""

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

import styles
import theme
from formatting import format_bytes, format_rate, format_temperature
from i18n import tr
from system_monitor import SystemReading

WIDTH = 320
PADDING = 14
ROW_HEIGHT = 22
HEADING_HEIGHT = 22
CORE_AREA_HEIGHT = 44
PROCESS_ROWS = 5
GAP_ABOVE_TASKBAR = 8


class HoverPanel(QWidget):
    """CPU cores, the busiest processes and each network adapter's speed."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._reading: SystemReading | None = None
        self._room = 0
        self._fit(None)

    @staticmethod
    def _room_now() -> int:
        """Space the active style's card needs around its face."""
        style = styles.current()
        return style.card_room("panel") if style.custom_painting else 0

    @staticmethod
    def _content_height(reading: SystemReading | None) -> int:
        adapters = max(1, len(reading.adapters)) if reading else 1
        processes = min(PROCESS_ROWS, len(reading.processes)) if reading else PROCESS_ROWS
        return (
            PADDING * 2
            + HEADING_HEIGHT + CORE_AREA_HEIGHT
            + HEADING_HEIGHT + max(1, processes) * ROW_HEIGHT
            + HEADING_HEIGHT + adapters * ROW_HEIGHT
        )

    def _fit(self, reading: SystemReading | None) -> None:
        """Size the window for the content plus the style's room."""
        self._room = self._room_now()
        self.setFixedSize(WIDTH + 2 * self._room, self._content_height(reading) + 2 * self._room)

    def set_reading(self, reading: SystemReading) -> None:
        self._reading = reading
        height = self._content_height(reading) + 2 * self._room_now()
        if height != self.height() or self._room != self._room_now():
            # Keep the bottom edge where it was: the panel sits above the taskbar.
            bottom = self.y() + self.height()
            old_room = self._room
            self._fit(reading)
            if self.isVisible():
                self.move(self.x() - (self._room - old_room), bottom - self.height()
                          + (self._room - old_room))
        self.update()

    def show_above(self, strip: QRect, taskbar: QRect, screen: QRect) -> None:
        """Open centred over the strip, clear of the taskbar. The card itself
        (inside its style's room) is what sits GAP_ABOVE_TASKBAR from the taskbar."""
        self._fit(self._reading)
        room = self._room
        x = strip.center().x() - self.width() // 2
        x = max(screen.left() + 4 - room, min(x, screen.right() - self.width() - 3 + room))
        if taskbar.top() > screen.top() + screen.height() // 2:  # taskbar at the bottom
            y = taskbar.top() - self.height() - GAP_ABOVE_TASKBAR + room
        else:
            y = taskbar.bottom() + GAP_ABOVE_TASKBAR - room
        self.move(QPoint(x, max(screen.top() + 4 - room, y)))
        self.show()

    # -- painting ---------------------------------------------------------

    def _heading(self, painter: QPainter, y: int, text: str, right: str = "") -> int:
        font = QFont("Segoe UI")
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.MUTED))
        area = QRectF(PADDING, y, WIDTH - PADDING * 2, HEADING_HEIGHT)
        painter.drawText(area, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         text.upper())
        if right:
            painter.drawText(area, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             right)
        return y + HEADING_HEIGHT

    @staticmethod
    def _cpu_color(percent: float) -> QColor:
        # A share of the whole processor, so 20% is already a lot for one app.
        if percent >= 50:
            return QColor(theme.RED)
        if percent >= 20:
            return QColor(theme.AMBER)
        return QColor(theme.TEXT)

    def _row(self, painter: QPainter, y: int, left: str, *columns: tuple[str, int, QColor | None]) -> None:
        """A name on the left and right-aligned (text, width, color) columns."""
        font = QFont("Segoe UI")
        font.setPixelSize(12)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        used = sum(width for _, width, _ in columns)
        name_width = WIDTH - PADDING * 2 - used - 6
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            QRectF(PADDING, y, name_width, ROW_HEIGHT),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(left, Qt.TextElideMode.ElideRight, int(name_width)),
        )
        x = WIDTH - PADDING - used
        for text, width, color in columns:
            painter.setPen(color or QColor(theme.MUTED))
            painter.drawText(
                QRectF(x, y, width, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            x += width

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        style = styles.current()
        room = self._room
        if style.custom_painting:
            face = QRectF(self.rect()).adjusted(room, room, -room, -room)
            # The panel is a window of its own, with nothing behind it. Some
            # styles' cards are see-through, so give them what they expect.
            painter.save()
            painter.setClipPath(style.card_path(face, "panel"))
            painter.fillRect(face, QColor(theme.BACKGROUND))
            if style.has_backdrop:
                painter.translate(face.topLeft())
                style.paint_backdrop(
                    painter, QRectF(0, 0, face.width(), face.height()), self.devicePixelRatioF()
                )
            painter.restore()
            style.paint_card(painter, face, "panel", None, self.devicePixelRatioF())
        else:
            painter.setPen(QPen(QColor(theme.CONTROL_BORDER), 1))
            painter.setBrush(QColor(theme.SURFACE))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.translate(room, room)
        reading = self._reading
        y = PADDING

        # CPU cores
        cpu_text = f"{reading.cpu_percent:.0f}%" if reading else ""
        if reading and reading.cpu_temperature_c is not None:
            cpu_text += f"  ·  {format_temperature(reading.cpu_temperature_c)}"
        y = self._heading(painter, y, tr("CPU cores"), cpu_text)
        cores = reading.cpu_per_core if reading else ()
        if cores:
            gap = 3
            width = min(18.0, (WIDTH - PADDING * 2 - gap * (len(cores) - 1)) / len(cores))
            x = float(PADDING)
            for percent in cores:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(theme.TRACK))
                painter.drawRoundedRect(QRectF(x, y, width, CORE_AREA_HEIGHT - 6), 3, 3)
                fill = (CORE_AREA_HEIGHT - 6) * max(0.0, min(100.0, percent)) / 100
                painter.setBrush(QColor(theme.level_color(percent, theme.ACCENT)))
                painter.drawRoundedRect(
                    QRectF(x, y + (CORE_AREA_HEIGHT - 6) - fill, width, fill), 3, 3
                )
                x += width + gap
        y += CORE_AREA_HEIGHT

        # Top processes
        y = self._heading(painter, y, tr("Top processes"))
        processes = reading.processes[:PROCESS_ROWS] if reading else ()
        if not processes:
            self._row(painter, y, tr("Waiting for data…"))
            y += ROW_HEIGHT
        for process in processes:
            self._row(
                painter, y, process.name,
                (f"{process.cpu_percent:.0f}%", 44, self._cpu_color(process.cpu_percent)),
                (format_bytes(process.memory_mb * 1024**2), 64, None),
            )
            y += ROW_HEIGHT

        # Network adapters
        y = self._heading(painter, y, tr("Network"))
        adapters = reading.adapters if reading else ()
        if not adapters:
            self._row(painter, y, tr("No active connection"))
        for adapter in adapters:
            self._row(
                painter, y, adapter.name,
                ("↓ " + format_rate(adapter.received_mbps), 92, QColor(theme.GREEN)),
                ("↑ " + format_rate(adapter.sent_mbps), 92, QColor(theme.ACCENT)),
            )
            y += ROW_HEIGHT
