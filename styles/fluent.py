# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Fluent: the look of Windows 11 settings. Calm rounded cards with fine borders,
accent buttons and switches that match the system's, and a thin bar."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen

import theme
from i18n import N_

from .base import Style
from .glass import shadow_outside
from .primitives import mix, with_alpha

ROOM = {"card": 6, "compact": 6, "group": 5, "panel": 8}
RADIUS = {"card": 8, "compact": 8, "group": 8, "panel": 8}


def _dark() -> bool:
    return theme.current == theme.DARK


class Fluent(Style):
    name = "fluent"
    label = N_("Fluent")
    description = N_("Calm cards and controls like Windows 11's own settings.")
    custom_painting = True
    hover_animation = True
    table_bars = True
    fonts = ("Segoe UI Variable Text", "Segoe UI")

    def palette(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                **theme.PALETTES[theme.DARK],
                "BACKGROUND": "#202020", "SURFACE": "#2b2b2b", "SURFACE_RAISED": "#323232",
                "BORDER": "#3b3b3b", "CONTROL_BORDER": "#4d4d4d", "TRACK": "#3d3d3d",
                "MUTED": "#b8b8b8", "DISABLED": "#707070", "TEXT": "#ffffff",
                "HOVER": "#393939", "PRESSED": "#2a2a2a", "SWITCH_OFF": "#2b2b2b",
                "ON_ACCENT": "#000000", "ACCENT": "#60cdff", "ACCENT_HOVER": "#7fd6ff",
                "GREEN": "#6ccb5f", "AMBER": "#fce100", "RED": "#ff99a4", "VIOLET": "#c5a3ff",
                "ORANGE": "#ff9d3c", "PINK": "#ff7bac", "LIME": "#9be85f",
                "SHADOW_DARK": "#70000000", "SHADOW_LIGHT": "#10ffffff",
            }
        return {
            **theme.PALETTES[theme.LIGHT],
            "BACKGROUND": "#f3f3f3", "SURFACE": "#ffffff", "SURFACE_RAISED": "#fbfbfb",
            "BORDER": "#e3e3e3", "CONTROL_BORDER": "#cfcfcf", "TRACK": "#e4e4e4",
            "MUTED": "#5c5c5c", "DISABLED": "#a8a8a8", "TEXT": "#1a1a1a",
            "HOVER": "#f0f0f0", "PRESSED": "#e5e5e5", "SWITCH_OFF": "#ffffff",
            "ON_ACCENT": "#ffffff", "ACCENT": "#0067c0", "ACCENT_HOVER": "#005a9e",
            "GREEN": "#0f7b0f", "AMBER": "#9d5d00", "RED": "#c42b1c", "VIOLET": "#5c2e91",
            "ORANGE": "#d83b01", "PINK": "#c239b3", "LIME": "#498205",
            "SHADOW_DARK": "#28000000", "SHADOW_LIGHT": "#ffffffff",
        }

    def stylesheet(self) -> str:
        fields = f"background: {theme.SURFACE_RAISED}; border: 1px solid {theme.CONTROL_BORDER};"
        return theme.custom_stylesheet(fields, radius=5)

    def card_room(self, kind: str) -> int:
        return ROOM.get(kind, 6)

    def card_radius(self, kind: str) -> float:
        return RADIUS.get(kind, 8)

    def button_room(self) -> int:
        return 3

    def toggle_size(self) -> QSize:
        return QSize(44, 22)

    # -- cards -----------------------------------------------------------------

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        dark = _dark()
        radius = self.card_radius(kind)
        shadow_outside(p, face, radius, QColor(0, 0, 0, 90 if dark else 26), 2, 5)
        p.setPen(QPen(QColor(255, 255, 255, 18) if dark else QColor(0, 0, 0, 22), 1))
        p.setBrush(QColor(theme.SURFACE))
        p.drawRoundedRect(face.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

    # -- buttons -----------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        dark = _dark()
        radius = face.height() / 2 if name == "pill" else 5
        accent = QColor(theme.ACCENT)
        if not enabled:
            p.setOpacity(0.45)
        box = face.adjusted(0.5, 0.5, -0.5, -0.5)
        if name == "primaryButton" or checked:
            fill = accent if not (pressed or checked and name != "primaryButton") else accent.darker(112)
            if name == "primaryButton":
                fill = mix(accent, theme.ACCENT_HOVER, hover) if not pressed else accent.darker(115)
            p.setPen(QPen(with_alpha("#000000", 0.18), 1))
            p.setBrush(fill)
            p.drawRoundedRect(box, radius, radius)
        else:
            if dark:
                strength = 0.06 + 0.04 * hover - (0.03 if pressed else 0)
                fill = QColor(255, 255, 255, round(255 * strength))
                border = QColor(255, 255, 255, 22)
            else:
                fill = mix("#ffffff", "#f6f6f6", hover) if not pressed else QColor("#f0f0f0")
                border = QColor("#d6d6d6")
            p.setPen(QPen(border, 1))
            p.setBrush(fill)
            p.drawRoundedRect(box, radius, radius)
            if not dark and not pressed:
                # The slightly darker lower edge of Windows 11 buttons.
                p.setPen(QPen(QColor(0, 0, 0, 38), 1))
                p.drawLine(box.left() + radius, box.bottom(), box.right() - radius, box.bottom())
        p.setOpacity(1.0)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        track = QRectF(rect).adjusted(0.5, 1.5, -0.5, -1.5)
        if not enabled:
            p.setOpacity(0.45)
        accent = QColor(theme.ACCENT)
        off_border = QColor(theme.MUTED)
        fill = mix(QColor(0, 0, 0, 0) if _dark() else QColor(255, 255, 255, 0), accent, progress)
        p.setPen(QPen(mix(off_border, accent, progress), 1))
        p.setBrush(fill)
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        diameter = 12 + 2 * progress
        knob = QRectF(track.left() + 4 + (track.width() - diameter - 8) * progress,
                      track.center().y() - diameter / 2, diameter, diameter)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(off_border, QColor(theme.ON_ACCENT), progress))
        p.drawEllipse(knob)
        p.setOpacity(1.0)

    # -- bars and gauges -----------------------------------------------------------

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        thin = rect.adjusted(0, 1, 0, -1) if rect.height() > 4 else rect
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.TRACK))
        p.drawRoundedRect(thin, 2, 2)

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        thin = rect.adjusted(0, 1, 0, -1) if rect.height() > 4 else rect
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(thin, 2, 2)
