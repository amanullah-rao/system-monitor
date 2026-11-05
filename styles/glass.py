# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Glass (glassmorphism): translucent frosted cards over a colorful backdrop, with a
bright edge on the side the light comes from and a fine grain."""

import random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

import theme
from i18n import N_

from . import primitives
from .base import Style
from .primitives import cast_shadow, mix, shape, with_alpha

ROOM = {"card": 14, "compact": 12, "group": 10, "panel": 14}
RADIUS = {"card": 18, "compact": 16, "group": 16, "panel": 16}

_grain: QPixmap | None = None


def _dark() -> bool:
    return theme.current == theme.DARK


def grain() -> QPixmap:
    """A small tile of faint noise, which makes the glass look frosted."""
    global _grain
    if _grain is None:
        rng = random.Random(7)
        image = QImage(96, 96, QImage.Format.Format_ARGB32)
        for x in range(96):
            for y in range(96):
                value = rng.randint(120, 255)
                image.setPixelColor(x, y, QColor(value, value, value, rng.randint(0, 16)))
        _grain = QPixmap.fromImage(image)
    return _grain


def shadow_outside(p: QPainter, face: QRectF, radius: float, color: QColor, dy: float,
                   blur: float) -> None:
    """A shadow that only shows around the card, not through its see-through face."""
    p.save()
    clip = QPainterPath()
    clip.addRect(face.adjusted(-60, -60, 60, 60))
    clip = clip.subtracted(shape(face, radius))
    p.setClipPath(clip)
    cast_shadow(p, face, radius, False, color, 0, dy, blur)
    p.restore()


class Glass(Style):
    name = "glass"
    label = N_("Glass")
    description = N_("Frosted, see-through cards over a colorful background.")
    custom_painting = True
    has_backdrop = True
    hover_animation = True
    table_bars = True
    fonts = ("Segoe UI Variable Text", "Segoe UI")

    def palette(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                **theme.PALETTES[theme.DARK],
                "BACKGROUND": "#0b1030", "SURFACE": "#1b2148", "SURFACE_RAISED": "#252c5a",
                "BORDER": "#3a4379", "CONTROL_BORDER": "#4d5896", "TRACK": "#2c3466",
                "MUTED": "#b9c2e2", "DISABLED": "#6c76a6", "TEXT": "#f4f7ff",
                "HOVER": "#2f3770", "PRESSED": "#222959", "SWITCH_OFF": "#2c3466",
                "ON_ACCENT": "#06122a", "ACCENT": "#7dd3fc", "ACCENT_HOVER": "#bae6fd",
                "GREEN": "#6ee7b7", "AMBER": "#fcd34d", "RED": "#fda4af", "VIOLET": "#c4b5fd",
                "ORANGE": "#fdba74", "PINK": "#f9a8d4", "LIME": "#bef264",
                "SHADOW_DARK": "#80000000", "SHADOW_LIGHT": "#20ffffff",
            }
        return {
            **theme.PALETTES[theme.LIGHT],
            "BACKGROUND": "#e6edfc", "SURFACE": "#f3f6ff", "SURFACE_RAISED": "#ffffff",
            "BORDER": "#cfd8f0", "CONTROL_BORDER": "#b9c5e6", "TRACK": "#d4dcf2",
            "MUTED": "#4a5878", "DISABLED": "#98a3c2", "TEXT": "#14213d",
            "HOVER": "#e8edfb", "PRESSED": "#d9e0f4", "SWITCH_OFF": "#c3cdea",
            "ON_ACCENT": "#ffffff", "ACCENT": "#2563eb", "ACCENT_HOVER": "#1d4ed8",
            "SHADOW_DARK": "#40283c78", "SHADOW_LIGHT": "#ffffffff",
        }

    def stylesheet(self) -> str:
        if _dark():
            fields = ("background: rgba(255, 255, 255, 0.10); "
                      "border: 1px solid rgba(255, 255, 255, 0.28);")
        else:
            fields = ("background: rgba(255, 255, 255, 0.65); "
                      "border: 1px solid rgba(20, 33, 61, 0.18);")
        return theme.custom_stylesheet(fields, radius=12, extra="QHeaderView { background: transparent; }")

    def card_room(self, kind: str) -> int:
        return ROOM.get(kind, 12)

    def card_radius(self, kind: str) -> float:
        return RADIUS.get(kind, 16)

    def button_room(self) -> int:
        return 7

    # -- cards -----------------------------------------------------------------

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        dark = _dark()
        radius = self.card_radius(kind)
        shadow_outside(p, face, radius, QColor(0, 0, 0, 120 if dark else 44), 6, 12)
        frost = QLinearGradient(face.topLeft(), face.bottomLeft())
        frost.setColorAt(0, QColor(255, 255, 255, 50 if dark else 165))
        frost.setColorAt(1, QColor(255, 255, 255, 18 if dark else 95))
        path = shape(face, radius)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(frost)
        p.drawPath(path)
        p.setBrush(QBrush(grain()))
        p.drawPath(path)
        edge = QLinearGradient(face.topLeft(), face.bottomRight())
        edge.setColorAt(0, QColor(255, 255, 255, 150 if dark else 235))
        edge.setColorAt(0.5, QColor(255, 255, 255, 45 if dark else 130))
        edge.setColorAt(1, QColor(255, 255, 255, 20 if dark else 80))
        p.setPen(QPen(QBrush(edge), 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(face.adjusted(0.6, 0.6, -0.6, -0.6), radius, radius)

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        dark = _dark()
        radius = face.height() / 2 if name in ("pill", "primaryButton") else 12
        accent = QColor(theme.ACCENT)
        if not enabled:
            p.setOpacity(0.45)
        if name == "primaryButton" and enabled:
            if not pressed:
                shadow_outside(p, face, radius, with_alpha(accent, 0.40 + 0.2 * hover), 3, 8)
            gradient = QLinearGradient(face.topLeft(), face.bottomLeft())
            gradient.setColorAt(0, with_alpha(accent.lighter(115 + round(10 * hover)), 0.95))
            gradient.setColorAt(1, with_alpha(accent, 0.80))
            p.setPen(QPen(QColor(255, 255, 255, 110), 1))
            p.setBrush(gradient)
            p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        else:
            strength = (0.10 if dark else 0.55) + 0.10 * hover + (0.05 if pressed else 0)
            fill = QColor(255, 255, 255, round(255 * min(strength, 0.9)))
            if checked:
                fill = with_alpha(accent, 0.32)
            p.setPen(QPen(QColor(255, 255, 255, round(255 * ((0.25 if dark else 0.7) + 0.3 * hover))), 1))
            p.setBrush(fill)
            p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.setOpacity(1.0)

    def toggle_size(self) -> QSize:
        return QSize(48, 27)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        dark = _dark()
        track = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        if not enabled:
            p.setOpacity(0.45)
        accent = QColor(theme.ACCENT)
        off = QColor(255, 255, 255, 36 if dark else 150)
        on = with_alpha(accent, 0.85)
        p.setPen(QPen(QColor(255, 255, 255, 110 if dark else 200), 1))
        p.setBrush(mix(off, on, progress))
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = track.height() - 6
        knob = QRectF(track.left() + 3 + (track.width() - diameter - 6) * progress,
                      track.top() + 3, diameter, diameter)
        cast_shadow(p, knob, 0, True, QColor(0, 0, 0, 90), 0, 1, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawEllipse(knob)
        p.setOpacity(1.0)

    # -- bars and gauges -----------------------------------------------------------

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 34) if _dark() else QColor(20, 33, 61, 26))
        p.drawRoundedRect(rect, radius, radius)

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        base = QColor(color)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0, base.lighter(118))
        gradient.setColorAt(1, base)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(rect, radius, radius)

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        pen = QPen(QColor(255, 255, 255, 38) if _dark() else QColor(20, 33, 61, 30), thickness)
        p.setPen(pen)
        p.drawEllipse(rect)
        if value is not None and value > 0:
            span = -int(min(value, 100.0) / 100 * 360 * 16)
            glow = QPen(with_alpha(color, 0.25), thickness + 6)
            glow.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow)
            p.drawArc(rect, 90 * 16, span)
            pen.setColor(color)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, span)

    # -- window background ---------------------------------------------------------

    def paint_backdrop(self, p: QPainter, rect: QRectF, dpr: float) -> None:
        dark = _dark()
        width, height = rect.width(), rect.height()
        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if dark:
            base.setColorAt(0, QColor("#0a0f2e"))
            base.setColorAt(0.55, QColor("#1b1654"))
            base.setColorAt(1, QColor("#0b2b4d"))
            blobs = ((0.10, 0.16, 0.55, "#ff4fd8", 0.34), (0.90, 0.30, 0.50, "#22d3ee", 0.28),
                     (0.52, 0.96, 0.60, "#fbbf24", 0.18))
        else:
            base.setColorAt(0, QColor("#dbeafe"))
            base.setColorAt(0.5, QColor("#ede9fe"))
            base.setColorAt(1, QColor("#fce7f3"))
            blobs = ((0.10, 0.15, 0.55, "#fda4af", 0.55), (0.90, 0.25, 0.50, "#7dd3fc", 0.55),
                     (0.50, 0.95, 0.60, "#c4b5fd", 0.50))
        p.fillRect(rect, base)
        reach = max(width, height)
        for cx, cy, radius, color, alpha in blobs:
            blob = QRadialGradient(QPointF(cx * width, cy * height), radius * reach)
            blob.setColorAt(0, with_alpha(color, alpha))
            blob.setColorAt(1, with_alpha(color, 0.0))
            p.fillRect(rect, blob)
