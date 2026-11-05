# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Soft (neumorphism): shapes that look pressed out of, or into, a surface of
one color, lit from the top left."""

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QPainter

import theme
from i18n import N_

from . import primitives
from .base import Style

DEPTH = {"card": 1.0, "compact": 0.8, "group": 0.7, "panel": 0.7}
RADIUS = {"card": 18, "compact": 16, "group": 16, "panel": 14}
BUTTON_DEPTH = 0.55


class Soft(Style):
    name = "soft"
    label = N_("Soft")
    description = N_("Rounded shapes that look pressed out of the surface.")
    custom_painting = True

    def palette(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                **theme.PALETTES[theme.DARK],
                "BACKGROUND": "#2a2f3b", "SURFACE": "#2a2f3b", "SURFACE_RAISED": "#2a2f3b",
                "BORDER": "#353c4b", "CONTROL_BORDER": "#3f4758", "TRACK": "#222730",
                "MUTED": "#a3aec2", "DISABLED": "#5f6a7e", "TEXT": "#edf1f8",
                "HOVER": "#303644", "PRESSED": "#262b36", "SWITCH_OFF": "#222730",
                "SHADOW_DARK": "#e6141820", "SHADOW_LIGHT": "#8c444d60",
            }
        return {
            **theme.PALETTES[theme.LIGHT],
            "BACKGROUND": "#e4e9f1", "SURFACE": "#e4e9f1", "SURFACE_RAISED": "#e4e9f1",
            "BORDER": "#d3dae6", "CONTROL_BORDER": "#c4cddb", "TRACK": "#d7deea",
            "MUTED": "#5d6a82", "DISABLED": "#a1abbd", "TEXT": "#232c3c",
            "HOVER": "#dbe1ec", "PRESSED": "#d2d9e6", "SWITCH_OFF": "#d7deea",
            "SHADOW_DARK": "#d4a3b1c6", "SHADOW_LIGHT": "#f2ffffff",
        }

    def stylesheet(self) -> str:
        dark_edge = theme.rgba(theme.SHADOW_DARK, 0.55)
        light_edge = theme.rgba(theme.SHADOW_LIGHT, 0.9)
        inset = (
            f"background: {theme.TRACK}; border: 2px solid {light_edge}; "
            f"border-top-color: {dark_edge}; border-left-color: {dark_edge}; "
            f"border-bottom-color: {light_edge}; border-right-color: {light_edge};"
        )
        return theme.custom_stylesheet(inset)

    def card_room(self, kind: str) -> int:
        return primitives.margin(DEPTH.get(kind, 1.0))

    def card_radius(self, kind: str) -> float:
        return RADIUS.get(kind, 16)

    def button_room(self) -> int:
        return primitives.margin(BUTTON_DEPTH)

    def toggle_size(self) -> QSize:
        return QSize(50, 28)

    def paint_card(self, painter: QPainter, face: QRectF, kind: str, accent: str | None,
                   dpr: float) -> None:
        primitives.paint_raised(painter, face, self.card_radius(kind),
                                depth=DEPTH.get(kind, 1.0), dpr=dpr)

    def paint_button(self, painter: QPainter, face: QRectF, name: str, pressed: bool,
                     hover: float, enabled: bool, checked: bool, dpr: float) -> None:
        radius = face.height() / 2 if name in ("pill", "primaryButton") else 12
        down = (pressed or checked) and enabled
        fill = theme.ACCENT if name == "primaryButton" and enabled else None
        if down:
            primitives.paint_inset(painter, face, radius, depth=BUTTON_DEPTH, fill=fill, dpr=dpr)
        else:
            primitives.paint_raised(painter, face, radius, depth=BUTTON_DEPTH, fill=fill, dpr=dpr)

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        """An inset slot with a raised knob."""
        track = QRectF(rect)
        primitives.paint_inset(p, track, track.height() / 2, depth=0.4, dpr=dpr)
        diameter = track.height() - 8
        left = 4 + (track.width() - diameter - 8) * progress
        knob = QRectF(left, 4, diameter, diameter)
        fill = primitives.mix(theme.SURFACE, theme.ACCENT, progress) if enabled else QColor(theme.SURFACE)
        primitives.paint_raised(p, knob, 0, ellipse=True, depth=0.2, fill=fill.name(), dpr=dpr)

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        primitives.paint_inset(p, rect, radius, depth=0.28, dpr=dpr)

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        inner = rect.adjusted(thickness + 5, thickness + 5, -(thickness + 5), -(thickness + 5))
        primitives.paint_raised(p, inner, 0, ellipse=True, depth=0.45, dpr=dpr)
        super().paint_ring(p, rect, thickness, value, color, dpr)
