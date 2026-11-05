# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""3D (skeuomorphic): panels, glossy buttons, recessed grooves and metal knobs that look
like real hardware."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)

import theme
from i18n import N_

from .base import Style
from .primitives import cast_shadow, mix, with_alpha

ROOM = {"card": 10, "compact": 9, "group": 7, "panel": 12}
RADIUS = {"card": 12, "compact": 12, "group": 10, "panel": 12}


def _dark() -> bool:
    return theme.current == theme.DARK


def _brushed(dark: bool) -> QPixmap:
    """A tile of fine horizontal lines, like brushed metal."""
    tile = QPixmap(4, 3)
    tile.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tile)
    painter.fillRect(0, 0, 4, 1, QColor(255, 255, 255, 9) if dark else QColor(0, 0, 0, 8))
    painter.end()
    return tile


def _screw(p: QPainter, cx: float, cy: float, dark: bool) -> None:
    radius = 3.4
    metal = QRadialGradient(QPointF(cx - 1, cy - 1), radius * 1.7)
    metal.setColorAt(0, QColor("#d9dce2") if dark else QColor("#f6f7f9"))
    metal.setColorAt(1, QColor("#5c616c") if dark else QColor("#8a8f9b"))
    p.setPen(QPen(QColor(0, 0, 0, 150 if dark else 100), 0.8))
    p.setBrush(metal)
    p.drawEllipse(QPointF(cx, cy), radius, radius)
    p.setPen(QPen(QColor(0, 0, 0, 160), 1.0))
    p.drawLine(QPointF(cx - 2.2, cy + 1.2), QPointF(cx + 2.2, cy - 1.2))


class Skeuo(Style):
    name = "skeuo"
    label = N_("3D")
    description = N_("Raised, glossy controls like real hardware.")
    custom_painting = True
    has_backdrop = True
    hover_animation = True
    table_bars = True

    def palette(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                **theme.PALETTES[theme.DARK],
                "BACKGROUND": "#1b1d22", "SURFACE": "#2c2f37", "SURFACE_RAISED": "#363a44",
                "BORDER": "#101216", "CONTROL_BORDER": "#4a4f5b", "TRACK": "#15171b",
                "MUTED": "#aeb4c1", "DISABLED": "#646a77", "TEXT": "#eef1f6",
                "HOVER": "#3e434e", "PRESSED": "#262930", "SWITCH_OFF": "#15171b",
                "ON_ACCENT": "#06182a", "ACCENT": "#4aaef8", "ACCENT_HOVER": "#7cc6fb",
                "GREEN": "#4ade80", "AMBER": "#fbbf24", "RED": "#f87171", "VIOLET": "#a78bfa",
                "ORANGE": "#fb923c", "PINK": "#f472b6", "LIME": "#a3e635",
                "SHADOW_DARK": "#aa000000", "SHADOW_LIGHT": "#18ffffff",
            }
        return {
            **theme.PALETTES[theme.LIGHT],
            "BACKGROUND": "#c8cbd1", "SURFACE": "#e2e4e8", "SURFACE_RAISED": "#eceef1",
            "BORDER": "#8d919b", "CONTROL_BORDER": "#9ea3ad", "TRACK": "#b3b7bf",
            "MUTED": "#454b57", "DISABLED": "#8d929d", "TEXT": "#1b1e25",
            "HOVER": "#f3f4f6", "PRESSED": "#d0d3d9", "SWITCH_OFF": "#b3b7bf",
            "ON_ACCENT": "#ffffff", "ACCENT": "#1b78d8", "ACCENT_HOVER": "#145fb0",
            "SHADOW_DARK": "#70000000", "SHADOW_LIGHT": "#ffffffff",
        }

    def stylesheet(self) -> str:
        fields = (f"background: {theme.TRACK}; border: 1px solid {theme.CONTROL_BORDER}; "
                  f"border-top-color: {theme.BORDER};")
        return theme.custom_stylesheet(fields, radius=7)

    def card_room(self, kind: str) -> int:
        return ROOM.get(kind, 9)

    def card_radius(self, kind: str) -> float:
        return RADIUS.get(kind, 10)

    def button_room(self) -> int:
        return 6

    def toggle_size(self) -> QSize:
        return QSize(52, 28)

    # -- cards -----------------------------------------------------------------

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        dark = _dark()
        radius = self.card_radius(kind)
        cast_shadow(p, face, radius, False, QColor(0, 0, 0, 175 if dark else 95), 0, 4, 9)
        panel = QLinearGradient(face.topLeft(), face.bottomLeft())
        panel.setColorAt(0, QColor("#3d414c") if dark else QColor("#f5f6f8"))
        panel.setColorAt(1, QColor("#252830") if dark else QColor("#d1d4da"))
        p.setPen(QPen(QColor("#0b0d10") if dark else QColor("#8a8e99"), 1))
        p.setBrush(panel)
        p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_brushed(dark)))
        p.drawRoundedRect(face.adjusted(1, 1, -1, -1), radius, radius)
        shine = QLinearGradient(face.topLeft(), QPointF(face.left(), face.top() + face.height() * 0.55))
        shine.setColorAt(0, QColor(255, 255, 255, 62 if dark else 230))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(QPen(QBrush(shine), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(face.adjusted(1.6, 1.6, -1.6, -1.6), radius - 1, radius - 1)
        if kind == "card":
            for cx in (face.left() + 8, face.right() - 8):
                for cy in (face.top() + 8, face.bottom() - 8):
                    _screw(p, cx, cy, dark)

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        dark = _dark()
        radius = face.height() / 2 if name == "pill" else 9
        if name == "primaryButton":
            base = QColor(theme.ACCENT)
        elif checked:
            base = QColor(theme.ACCENT).darker(110)
        else:
            base = QColor("#4a4f5b") if dark else QColor("#f1f2f5")
        if not enabled:
            p.setOpacity(0.5)
        down = pressed or checked
        if not down:
            cast_shadow(p, face, radius, False, QColor(0, 0, 0, 150 if dark else 80), 0, 2, 4)
        top = base.lighter(128 + round(10 * hover)) if not down else base.darker(118)
        bottom = base.darker(122) if not down else base.darker(105)
        body = QLinearGradient(face.topLeft(), face.bottomLeft())
        body.setColorAt(0, top)
        body.setColorAt(1, bottom)
        p.setPen(QPen(QColor(0, 0, 0, 190 if dark else 120), 1))
        p.setBrush(body)
        p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if not down:
            gloss = QRectF(face.left() + 2, face.top() + 1.5, face.width() - 4, face.height() * 0.46)
            shine = QLinearGradient(gloss.topLeft(), gloss.bottomLeft())
            shine.setColorAt(0, QColor(255, 255, 255, 105))
            shine.setColorAt(1, QColor(255, 255, 255, 14))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shine)
            p.drawRoundedRect(gloss, max(radius - 2, 2), max(radius - 2, 2))
        else:
            inner = QLinearGradient(face.topLeft(), QPointF(face.left(), face.top() + face.height() * 0.5))
            inner.setColorAt(0, QColor(0, 0, 0, 90))
            inner.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(inner)
            p.drawRoundedRect(face.adjusted(1, 1, -1, -1), radius, radius)
        p.setOpacity(1.0)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        dark = _dark()
        groove = QRectF(rect).adjusted(0.5, 3.5, -0.5, -3.5)
        if not enabled:
            p.setOpacity(0.5)
        slot = QLinearGradient(groove.topLeft(), groove.bottomLeft())
        slot.setColorAt(0, QColor("#0d0f12") if dark else QColor("#8d929c"))
        slot.setColorAt(1, QColor("#22252b") if dark else QColor("#c5c8cf"))
        p.setPen(QPen(QColor(0, 0, 0, 200 if dark else 110), 1))
        p.setBrush(slot)
        p.drawRoundedRect(groove, groove.height() / 2, groove.height() / 2)
        lit = QRectF(groove.left() + 1.5, groove.top() + 1.5,
                     (groove.width() - 3) * (0.2 + 0.8 * progress) * min(progress * 4, 1.0),
                     groove.height() - 3)
        if progress > 0.02:
            glow = QColor(theme.ACCENT)
            fill = QLinearGradient(lit.topLeft(), lit.bottomLeft())
            fill.setColorAt(0, glow.lighter(125))
            fill.setColorAt(1, glow.darker(115))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(lit, lit.height() / 2, lit.height() / 2)
        diameter = rect.height() - 2
        knob = QRectF(rect.left() + 1 + (rect.width() - diameter - 2) * progress,
                      rect.top() + 1, diameter, diameter)
        cast_shadow(p, knob, 0, True, QColor(0, 0, 0, 170), 0, 2, 4)
        metal = QRadialGradient(QPointF(knob.center().x() - 3, knob.center().y() - 4), diameter * 0.75)
        metal.setColorAt(0, QColor("#f7f8fa"))
        metal.setColorAt(0.55, QColor("#bcc0c8"))
        metal.setColorAt(1, QColor("#7c818c"))
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.setBrush(metal)
        p.drawEllipse(knob)
        p.setOpacity(1.0)

    # -- bars and gauges -----------------------------------------------------------

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        dark = _dark()
        groove = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        groove.setColorAt(0, QColor("#0b0d10") if dark else QColor("#8d929c"))
        groove.setColorAt(1, QColor("#23262c") if dark else QColor("#c7cad1"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(groove)
        p.drawRoundedRect(rect, radius, radius)

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        base = QColor(color)
        body = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        body.setColorAt(0, base.lighter(140))
        body.setColorAt(1, base.darker(120))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(body)
        p.drawRoundedRect(rect, radius, radius)

    def ring_text_color(self) -> QColor:
        # The gauge face is dark glass in both the dark and the light theme.
        return QColor("#f1f3f7")

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        dark = _dark()
        outer = rect.adjusted(-thickness / 2, -thickness / 2, thickness / 2, thickness / 2)
        bezel = QLinearGradient(outer.topLeft(), outer.bottomRight())
        bezel.setColorAt(0, QColor("#e9ebef"))
        bezel.setColorAt(0.5, QColor("#8f949f"))
        bezel.setColorAt(1, QColor("#4b4f59"))
        p.setPen(QPen(QColor(0, 0, 0, 160), 1))
        p.setBrush(bezel)
        p.drawEllipse(outer.adjusted(0.5, 0.5, -0.5, -0.5))
        face = outer.adjusted(5, 5, -5, -5)
        glass = QRadialGradient(face.center(), face.width() / 2)
        glass.setColorAt(0, QColor("#1d2027") if dark else QColor("#2b2f38"))
        glass.setColorAt(1, QColor("#0d0f13"))
        p.setPen(QPen(QColor(0, 0, 0, 220), 1))
        p.setBrush(glass)
        p.drawEllipse(face)
        thin = thickness * 0.62
        inner = face.adjusted(4 + thin / 2, 4 + thin / 2, -(4 + thin / 2), -(4 + thin / 2))
        pen = QPen(QColor("#3a3f49"), thin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(inner)
        if value is not None and value > 0:
            span = -int(min(value, 100.0) / 100 * 360 * 16)
            pen.setColor(color)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(inner, 90 * 16, span)
        dome = QRectF(face.left() + face.width() * 0.14, face.top() + 2,
                      face.width() * 0.72, face.height() * 0.42)
        shine = QLinearGradient(dome.topLeft(), dome.bottomLeft())
        shine.setColorAt(0, QColor(255, 255, 255, 70))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shine)
        p.drawEllipse(dome)

    # -- window background ---------------------------------------------------------

    def paint_backdrop(self, p: QPainter, rect: QRectF, dpr: float) -> None:
        dark = _dark()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor("#2a2d34") if dark else QColor("#d9dce1"))
        gradient.setColorAt(1, QColor("#15171b") if dark else QColor("#b6bac2"))
        p.fillRect(rect, gradient)
        p.fillRect(rect, QBrush(_brushed(dark)))
