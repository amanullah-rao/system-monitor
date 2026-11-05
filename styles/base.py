# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""What a style is.

A style supplies its colors and stylesheet, and, when it draws the interface
itself (``custom_painting``), how cards, buttons, switches, bars and gauges
look. This base class is the Classic style: flat, with the widgets' own
drawing, so a style only overrides what it changes.
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPainterPath, QPen, QPixmap

import theme
from i18n import N_

from . import primitives


class Style:
    name = "classic"
    label = N_("Classic")
    description = N_("Flat cards with thin outlines.")

    # True when the style draws cards, buttons and so on itself.
    custom_painting = False
    # Draws the window background (a gradient, a grid, …).
    has_backdrop = False
    # The style has no light variant.
    always_dark = False
    # A short colored bar on each dashboard card instead of its colored dot.
    card_accent_bar = False
    # Buttons fade in their hover color.
    hover_animation = False
    # Charts draw their lines with a glow.
    chart_glow = False
    # The dashboard's table rows draw their CPU bars with the style's bar
    # drawing too (otherwise they stay plain).
    table_bars = False
    # Typefaces to try for the interface, best first.
    fonts: tuple[str, ...] = ("Segoe UI",)

    # -- colors and stylesheet -------------------------------------------------

    def palette(self, dark: bool) -> dict[str, str]:
        return dict(theme.PALETTES[theme.DARK if dark else theme.LIGHT])

    def stylesheet(self) -> str:
        return theme.classic_stylesheet()

    def font_family(self) -> str:
        installed = set(QFontDatabase.families())
        return next((family for family in self.fonts if family in installed), "Segoe UI")

    # -- geometry --------------------------------------------------------------

    def card_room(self, kind: str) -> int:
        """Space a card leaves around its content for its own shadow or glow."""
        return 0

    def card_radius(self, kind: str) -> float:
        return 14

    def button_room(self) -> int:
        return 0

    def toggle_size(self) -> QSize:
        return QSize(44, 24)

    # -- cards -----------------------------------------------------------------

    def card_path(self, face: QRectF, kind: str) -> QPainterPath:
        """The outline of a card's face, for clipping things to it."""
        return primitives.shape(face, self.card_radius(kind))

    def draw_card(self, p: QPainter, face: QRectF, kind: str, accent: QColor | None) -> None:
        """Draw a card whose face is `face`, with the style's shadow around it."""

    def paint_card(self, painter: QPainter, face: QRectF, kind: str, accent: str | None,
                   dpr: float) -> None:
        room = self.card_room(kind)
        width, height = math.ceil(face.width()), math.ceil(face.height())
        key = (self.name, theme.current, "card", kind, width, height, accent, dpr)
        pixmap = primitives.cache_get(key)
        if pixmap is None:
            pixmap = QPixmap(int((width + room * 2) * dpr), int((height + room * 2) * dpr))
            pixmap.setDevicePixelRatio(dpr)
            pixmap.fill(Qt.GlobalColor.transparent)
            drawing = QPainter(pixmap)
            drawing.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.draw_card(drawing, QRectF(room, room, face.width(), face.height()), kind,
                           QColor(accent) if accent else None)
            drawing.end()
            primitives.cache_put(key, pixmap)
        painter.drawPixmap(QPointF(face.left() - room, face.top() - room), pixmap)

    # -- buttons ---------------------------------------------------------------

    def draw_button(self, p: QPainter, face: QRectF, name: str, pressed: bool, hover: float,
                    enabled: bool, checked: bool) -> None:
        """Draw a button's background; the label is drawn by the widget."""

    def paint_button(self, painter: QPainter, face: QRectF, name: str, pressed: bool,
                     hover: float, enabled: bool, checked: bool, dpr: float) -> None:
        room = self.button_room()
        width, height = math.ceil(face.width()), math.ceil(face.height())
        level = round(hover * 4)  # a few steps are enough, and keep the cache small
        key = (self.name, theme.current, "button", name, width, height, pressed, level,
               enabled, checked, dpr)
        pixmap = primitives.cache_get(key)
        if pixmap is None:
            pixmap = QPixmap(int((width + room * 2) * dpr), int((height + room * 2) * dpr))
            pixmap.setDevicePixelRatio(dpr)
            pixmap.fill(Qt.GlobalColor.transparent)
            drawing = QPainter(pixmap)
            drawing.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.draw_button(drawing, QRectF(room, room, face.width(), face.height()), name,
                             pressed, level / 4, enabled, checked)
            drawing.end()
            primitives.cache_put(key, pixmap)
        painter.drawPixmap(QPointF(face.left() - room, face.top() - room), pixmap)

    # -- switches, bars and gauges (these are the Classic drawings) --------------

    def paint_toggle(self, p: QPainter, rect: QRectF, progress: float, enabled: bool,
                     dpr: float) -> None:
        """A switch; `progress` is 0 (off) to 1 (on) while its knob slides."""
        p.setPen(Qt.PenStyle.NoPen)
        track = primitives.mix(theme.SWITCH_OFF, theme.ACCENT, progress)
        knob = QColor("#ffffff")
        if not enabled:
            track.setAlpha(80)
            knob = QColor(theme.DISABLED)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)
        p.setBrush(knob)
        p.drawEllipse(QRectF(2 + 20 * progress, 2, 20, 20))

    def paint_track(self, p: QPainter, rect: QRectF, radius: float, dpr: float) -> None:
        """The empty part of a bar."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.TRACK))
        p.drawRoundedRect(rect, radius, radius)

    def paint_bar_fill(self, p: QPainter, rect: QRectF, color: str, radius: float) -> None:
        """The filled part of a bar."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(rect, radius, radius)

    def paint_ring(self, p: QPainter, rect: QRectF, thickness: float, value: float | None,
                   color: QColor, dpr: float) -> None:
        """A circular gauge: a track with an arc filled from the top, clockwise."""
        pen = QPen(QColor(theme.TRACK), thickness)
        p.setPen(pen)
        p.drawEllipse(rect)
        if value is not None and value > 0:
            pen.setColor(color)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            span = -int(min(value, 100.0) / 100 * 360 * 16)
            p.drawArc(rect, 90 * 16, span)

    def ring_text_color(self) -> QColor:
        """The color of the number in the middle of a circular gauge."""
        return QColor(theme.TEXT)

    # -- window background -----------------------------------------------------

    def paint_backdrop(self, p: QPainter, rect: QRectF, dpr: float) -> None:
        """Paint behind everything in a window (only when has_backdrop)."""

