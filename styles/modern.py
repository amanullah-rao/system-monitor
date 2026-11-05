# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Modern: a clean, premium dashboard look. Rounded cards with a soft shadow and a
colored accent bar, gradient accent buttons, switches that slide, and gentle
hover fades."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QRadialGradient

import theme
from i18n import N_

from . import primitives
from .base import Style
from .primitives import cast_shadow, mix, with_alpha

ROOM = {"card": 10, "compact": 9, "group": 7, "panel": 12}
RADIUS = {"card": 16, "compact": 14, "group": 14, "panel": 14}


def _dark() -> bool:
    return theme.current == theme.DARK


class Modern(Style):
    name = "modern"
    label = N_("Modern")
    description = N_("Clean cards with soft shadows and a colored accent on each card.")
    custom_painting = True
    has_backdrop = True
    card_accent_bar = True
    hover_animation = True
    table_bars = True
    fonts = ("Segoe UI Variable Text", "Segoe UI")

    def palette(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                **theme.PALETTES[theme.DARK],
                "BACKGROUND": "#0e1220", "SURFACE": "#161b2e", "SURFACE_RAISED": "#1d2338",
                "BORDER": "#272e49", "CONTROL_BORDER": "#313a59", "TRACK": "#222944",
                "MUTED": "#8f99b8", "DISABLED": "#4d5675", "TEXT": "#eef1fb",
                "HOVER": "#252c48", "PRESSED": "#1a2036", "SWITCH_OFF": "#2b3354",
                "ON_ACCENT": "#ffffff", "ACCENT": "#818cf8", "ACCENT_HOVER": "#a5b4fc",
                "SHADOW_DARK": "#99000000", "SHADOW_LIGHT": "#10ffffff",
            }
        return {
            **theme.PALETTES[theme.LIGHT],
            "BACKGROUND": "#f3f5fb", "SURFACE": "#ffffff", "SURFACE_RAISED": "#f1f4fa",
            "BORDER": "#e2e7f1", "CONTROL_BORDER": "#d2d9e9", "TRACK": "#e6eaf4",
            "MUTED": "#62708b", "DISABLED": "#a8b1c6", "TEXT": "#0f1a33",
            "HOVER": "#edf1fa", "PRESSED": "#e2e7f3", "SWITCH_OFF": "#cad2e3",
            "ON_ACCENT": "#ffffff", "ACCENT": "#4f46e5", "ACCENT_HOVER": "#4338ca",
            "SHADOW_DARK": "#28141e3c", "SHADOW_LIGHT": "#ffffffff",
        }

    def stylesheet(self) -> str:
        fields = f"background: {theme.SURFACE_RAISED}; border: 1px solid {theme.CONTROL_BORDER};"
        return theme.custom_stylesheet(fields, radius=10)

    def card_room(self, kind: str) -> int:
        return ROOM.get(kind, 9)

    def card_radius(self, kind: str) -> float:
        return RADIUS.get(kind, 14)

    def button_room(self) -> int:
        return 6

    # -- cards -----------------------------------------------------------------

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        dark = _dark()
        radius = self.card_radius(kind)
        cast_shadow(p, face, radius, False, QColor(0, 0, 0, 150 if dark else 42), 0, 3, 10)
        fill = QLinearGradient(face.topLeft(), face.bottomLeft())
        fill.setColorAt(0, QColor(theme.SURFACE).lighter(106 if dark else 100))
        fill.setColorAt(1, QColor(theme.SURFACE))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(fill)
        p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        if accent is not None and kind == "card":
            bar = QRectF(face.left() + 20, face.top() + 1, 34, 3)
            gradient = QLinearGradient(bar.topLeft(), bar.topRight())
            gradient.setColorAt(0, accent)
            gradient.setColorAt(1, accent.lighter(135))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gradient)
            p.drawRoundedRect(bar, 1.5, 1.5)

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        dark = _dark()
        radius = face.height() / 2 if name == "pill" else 10
        accent = QColor(theme.ACCENT)
        if name == "primaryButton" and enabled:
            if not pressed:
                cast_shadow(p, face, radius, False, with_alpha(accent, 0.35 + 0.2 * hover), 0, 3, 7)
            gradient = QLinearGradient(face.topLeft(), face.bottomLeft())
            lift = 112 + round(10 * hover)
            gradient.setColorAt(0, accent.darker(112) if pressed else accent.lighter(lift))
            gradient.setColorAt(1, accent.darker(125) if pressed else accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gradient)
            p.drawRoundedRect(face, radius, radius)
            return
        if checked:
            fill = with_alpha(accent, 0.20)
            border = accent
        else:
            fill = mix(theme.SURFACE_RAISED, theme.HOVER, hover)
            if pressed:
                fill = QColor(theme.PRESSED)
            border = mix(theme.CONTROL_BORDER, accent, hover)
        if not enabled:
            fill.setAlphaF(fill.alphaF() * 0.5)
            border.setAlphaF(0.5)
        elif not pressed and not checked:
            cast_shadow(p, face, radius, False, QColor(0, 0, 0, 90 if dark else 22), 0, 1.5, 4)
        p.setPen(QPen(border, 1))
        p.setBrush(fill)
        p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    def toggle_size(self) -> QSize:
        return QSize(46, 26)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        track = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        if not enabled:
            p.setOpacity(0.45)
        accent = QColor(theme.ACCENT)
        gradient = QLinearGradient(track.topLeft(), track.topRight())
        gradient.setColorAt(0, mix(theme.SWITCH_OFF, accent.lighter(115), progress))
        gradient.setColorAt(1, mix(theme.SWITCH_OFF, accent, progress))
        p.setPen(QPen(mix(theme.CONTROL_BORDER, accent, progress), 1))
        p.setBrush(gradient)
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = track.height() - 6
        knob = QRectF(track.left() + 3 + (track.width() - diameter - 6) * progress,
                      track.top() + 3, diameter, diameter)
        cast_shadow(p, knob, 0, True, QColor(0, 0, 0, 110), 0, 1, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(theme.MUTED, "#ffffff", progress) if _dark() else QColor("#ffffff"))
        p.drawEllipse(knob)
        p.setOpacity(1.0)

    # -- bars and gauges -----------------------------------------------------------

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        base = QColor(color)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        gradient.setColorAt(0, base.lighter(120))
        gradient.setColorAt(1, base)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gradient)
        p.drawRoundedRect(rect, radius, radius)

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        pen = QPen(QColor(theme.TRACK), thickness)
        p.setPen(pen)
        p.drawEllipse(rect)
        if value is not None and value > 0:
            span = -int(min(value, 100.0) / 100 * 360 * 16)
            glow = QPen(with_alpha(color, 0.22), thickness + 6)
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
        top = QColor(theme.BACKGROUND).lighter(118) if dark else QColor("#fbfcff")
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, QColor(theme.BACKGROUND))
        p.fillRect(rect, gradient)
        glow = QRadialGradient(QPointF(rect.width() * 0.88, -rect.height() * 0.02),
                               max(rect.width(), rect.height()) * 0.7)
        glow.setColorAt(0, with_alpha(theme.ACCENT, 0.13 if dark else 0.10))
        glow.setColorAt(1, with_alpha(theme.ACCENT, 0.0))
        p.fillRect(rect, glow)
