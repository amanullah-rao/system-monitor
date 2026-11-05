# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""HUD (sci-fi): luminous panels with cut corners and glowing outlines, segmented
bars and gauges, a technical grid behind everything. Always dark."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient

import theme
from i18n import N_

from .base import Style
from .primitives import chamfered, glow_path, mix, with_alpha

ROOM = {"card": 8, "compact": 7, "group": 6, "panel": 9}
CUT = {"card": 14, "compact": 11, "group": 10, "panel": 12}
BLOCK = 5.0
BLOCK_GAP = 2.0
SEGMENTS = 48


def _brackets(p: QPainter, face: QRectF, color: QColor, length: float = 14) -> None:
    """Bright L-shaped marks at the two corners that are not cut."""
    pen = QPen(color, 2)
    pen.setCapStyle(Qt.PenCapStyle.SquareCap)
    p.setPen(pen)
    right, top, left, bottom = face.right() - 0.5, face.top() + 0.5, face.left() + 0.5, face.bottom() - 0.5
    p.drawLine(QPointF(right - length, top), QPointF(right, top))
    p.drawLine(QPointF(right, top), QPointF(right, top + length))
    p.drawLine(QPointF(left, bottom - length), QPointF(left, bottom))
    p.drawLine(QPointF(left, bottom), QPointF(left + length, bottom))


class Hud(Style):
    name = "hud"
    label = N_("HUD")
    description = N_("Glowing panels and segmented gauges, like a futuristic display. Always dark.")
    custom_painting = True
    has_backdrop = True
    always_dark = True
    hover_animation = True
    chart_glow = True
    table_bars = True
    fonts = ("Cascadia Mono", "Cascadia Code", "Consolas")

    def palette(self, dark: bool) -> dict[str, str]:
        return {
            **theme.PALETTES[theme.DARK],
            "BACKGROUND": "#050b14", "SURFACE": "#0a1626", "SURFACE_RAISED": "#0e1d31",
            "BORDER": "#12486a", "CONTROL_BORDER": "#1c6f99", "TRACK": "#0c2236",
            "MUTED": "#74a9be", "DISABLED": "#385567", "TEXT": "#d9f4ff",
            "HOVER": "#0f2740", "PRESSED": "#0a1c30", "SWITCH_OFF": "#0c2236",
            "ON_ACCENT": "#001018", "ACCENT": "#00e5ff", "ACCENT_HOVER": "#6af2ff",
            "GREEN": "#39ff88", "AMBER": "#ffb020", "RED": "#ff3b5c", "VIOLET": "#b388ff",
            "ORANGE": "#ff8a3d", "PINK": "#ff4fd8", "LIME": "#c6ff3d", "OVERLAY": "0, 229, 255",
            "SHADOW_DARK": "#cc000000", "SHADOW_LIGHT": "#1000e5ff",
        }

    def stylesheet(self) -> str:
        fields = (f"background: {theme.rgba(theme.ACCENT, 0.06)}; "
                  f"border: 1px solid {theme.rgba(theme.ACCENT, 0.55)};")
        return theme.custom_stylesheet(fields, radius=2, extra="QHeaderView { background: transparent; }")

    def card_room(self, kind: str) -> int:
        return ROOM.get(kind, 7)

    def card_radius(self, kind: str) -> float:
        return 0

    def card_path(self, face: QRectF, kind: str):
        return chamfered(face.adjusted(0.5, 0.5, -0.5, -0.5), CUT.get(kind, 10), "tl,br")

    def button_room(self) -> int:
        return 6

    def toggle_size(self) -> QSize:
        return QSize(50, 26)

    # -- cards -----------------------------------------------------------------

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        tint = accent or QColor(theme.ACCENT)
        edge = mix(theme.ACCENT, tint, 0.6)
        path = chamfered(face.adjusted(0.5, 0.5, -0.5, -0.5), CUT.get(kind, 10), "tl,br")
        fill = QLinearGradient(face.topLeft(), face.bottomRight())
        fill.setColorAt(0, with_alpha(tint, 0.11))
        fill.setColorAt(1, with_alpha(tint, 0.025))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
        glow_path(p, path, with_alpha(edge, 0.85), core=1.0, spread=6.0, strength=0.5)
        if kind in ("card", "panel"):
            _brackets(p, face, with_alpha(tint, 1.0))

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        accent = QColor(theme.ACCENT)
        path = chamfered(face.adjusted(0.5, 0.5, -0.5, -0.5), 6, "tl,br")
        if not enabled:
            p.setOpacity(0.4)
        if name == "primaryButton":
            fill = with_alpha(accent, 0.92 - (0.22 if pressed else 0) + 0.08 * hover)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawPath(path)
            glow_path(p, path, with_alpha(accent, 1.0), core=1.0, spread=5.0, strength=0.4 + 0.4 * hover)
        else:
            lit = 0.28 if checked else 0.0
            strength = 0.05 + 0.10 * hover + (0.18 if pressed else 0) + lit
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(with_alpha(accent, strength))
            p.drawPath(path)
            border = with_alpha(accent, 0.45 + 0.5 * hover + (0.3 if checked else 0))
            if hover > 0.4 or checked:
                glow_path(p, path, border, core=1.0, spread=4.0, strength=0.35)
            else:
                p.setPen(QPen(border, 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
        p.setOpacity(1.0)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        accent = QColor(theme.ACCENT)
        slot = QRectF(rect).adjusted(0.5, 2.5, -0.5, -2.5)
        if not enabled:
            p.setOpacity(0.4)
        color = mix(theme.MUTED, accent, progress)
        p.setPen(QPen(with_alpha(color, 0.85), 1))
        p.setBrush(with_alpha(accent, 0.04 + 0.2 * progress))
        p.drawPath(chamfered(slot, 5, "tl,br"))
        size = slot.height() - 6
        knob = QRectF(slot.left() + 3 + (slot.width() - size - 6) * progress,
                      slot.top() + 3, size, size)
        path = chamfered(knob, 3, "tl,br")
        if progress > 0.5:
            glow_path(p, path, with_alpha(accent, 1.0), core=1.0, spread=4.0, strength=0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(path)
        p.setOpacity(1.0)

    # -- bars and gauges -----------------------------------------------------------

    def _blocks(self, p: QPainter, rect: QRectF, count: int, color: QColor) -> None:
        pitch = BLOCK + BLOCK_GAP
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        for index in range(count):
            p.drawRect(QRectF(rect.left() + index * pitch, rect.top(), BLOCK, rect.height()))

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        count = max(1, int((rect.width() + BLOCK_GAP) // (BLOCK + BLOCK_GAP)))
        self._blocks(p, rect, count, with_alpha(theme.ACCENT, 0.14))

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        pitch = BLOCK + BLOCK_GAP
        count = max(1, round(rect.width() / pitch))
        base = QColor(color)
        halo = QRectF(rect.left() - 1, rect.top() - 1, rect.width() + 2, rect.height() + 2)
        self._blocks(p, halo, count, with_alpha(base, 0.22))
        self._blocks(p, rect, count, base)

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        step = 360 / SEGMENTS
        sweep = step - 3.0
        lit = round(min(max(value or 0.0, 0.0), 100.0) / 100 * SEGMENTS)
        pen = QPen()
        pen.setWidthF(thickness * 0.85)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        dim = with_alpha(theme.ACCENT, 0.15)
        glow = with_alpha(color, 0.22)
        for index in range(SEGMENTS):
            start = int((90 - index * step - sweep) * 16)
            if index < lit:
                pen.setColor(glow)
                pen.setWidthF(thickness + 3)
                p.setPen(pen)
                p.drawArc(rect, start, int(sweep * 16))
                pen.setWidthF(thickness * 0.85)
                pen.setColor(color)
            else:
                pen.setColor(dim)
            p.setPen(pen)
            p.drawArc(rect, start, int(sweep * 16))
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.4), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect.adjusted(thickness + 4, thickness + 4, -(thickness + 4), -(thickness + 4)))

    # -- window background ---------------------------------------------------------

    def paint_backdrop(self, p: QPainter, rect: QRectF, dpr: float) -> None:
        p.fillRect(rect, QColor(theme.BACKGROUND))
        glow = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.8)
        glow.setColorAt(0, QColor("#0a2036"))
        glow.setColorAt(1, QColor(theme.BACKGROUND))
        p.fillRect(rect, glow)
        p.setPen(QPen(with_alpha(theme.ACCENT, 0.05), 1))
        step = 32
        x = 0.0
        while x < rect.width():
            p.drawLine(QPointF(x + 0.5, 0), QPointF(x + 0.5, rect.height()))
            x += step
        y = 0.0
        while y < rect.height():
            p.drawLine(QPointF(0, y + 0.5), QPointF(rect.width(), y + 0.5))
            y += step
