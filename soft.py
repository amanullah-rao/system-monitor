# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""The Soft style (neumorphism): shapes that look pressed out of, or into, a
surface of one color, lit from the top left.

A raised shape has a light shadow up and to the left and a dark one down and
to the right; an inset shape has them the other way round, inside. Qt gives a
widget only one shadow, so these are drawn by hand into pixmaps, which are
cached per size so painting stays cheap.
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QStyle, QStyleOptionButton, QWidget

import theme

# Shadow size of a card at full "depth"; smaller things use a fraction of it.
OFFSET = 4.0
BLUR = 8.0
LAYERS = 8
CARD_RADIUS = 18
CACHE_LIMIT = 120

_cache: dict[tuple, QPixmap] = {}


def clear_cache() -> None:
    _cache.clear()


def margin(depth: float = 1.0) -> int:
    """Room a raised shape's shadow needs around it."""
    return math.ceil((OFFSET + BLUR) * depth) + 1


def _shape(rect: QRectF, radius: float, ellipse: bool, grow: float = 0.0) -> QPainterPath:
    path = QPainterPath()
    box = rect.adjusted(-grow, -grow, grow, grow)
    if ellipse:
        path.addEllipse(box)
    else:
        path.addRoundedRect(box, max(0.0, radius + grow), max(0.0, radius + grow))
    return path


def _intensity(grow: float, blur: float) -> float:
    return (1 - grow / blur) ** 2


def _cast_outer(
    painter: QPainter, rect: QRectF, radius: float, ellipse: bool, color: QColor,
    dx: float, dy: float, blur: float,
) -> None:
    """A soft shadow around the shape, moved by (dx, dy)."""
    base = color.alphaF()
    painter.setPen(Qt.PenStyle.NoPen)
    for layer in range(LAYERS):
        grow = blur * (LAYERS - layer) / LAYERS
        inner = blur * (LAYERS - layer - 1) / LAYERS
        alpha = base * (_intensity(inner, blur) - _intensity(grow, blur))
        shade = QColor(color)
        shade.setAlphaF(max(0.0, min(1.0, alpha)))
        painter.setBrush(shade)
        painter.drawPath(_shape(rect.translated(dx, dy), radius, ellipse, grow))


def _cast_inner(
    painter: QPainter, rect: QRectF, radius: float, ellipse: bool, color: QColor,
    dx: float, dy: float, blur: float,
) -> None:
    """A soft shadow just inside the shape, falling from (dx, dy)."""
    painter.save()
    painter.setClipPath(_shape(rect, radius, ellipse))
    painter.setPen(Qt.PenStyle.NoPen)
    base = color.alphaF()
    wide = QPainterPath()
    wide.addRect(rect.adjusted(-60, -60, 60, 60))
    for layer in range(LAYERS):
        shrink = blur * (LAYERS - layer) / LAYERS
        inner = blur * (LAYERS - layer - 1) / LAYERS
        alpha = base * (_intensity(inner, blur) - _intensity(shrink, blur))
        shade = QColor(color)
        shade.setAlphaF(max(0.0, min(1.0, alpha)))
        hole = _shape(rect.translated(dx, dy), radius, ellipse, -shrink)
        painter.fillPath(wide.subtracted(hole), shade)
    painter.restore()


def _key(kind: str, rect: QRectF, radius: float, ellipse: bool, depth: float,
         fill: str, dpr: float) -> tuple:
    return (kind, round(rect.width()), round(rect.height()), round(radius, 1), ellipse,
            depth, fill, theme.current, theme.current_style, dpr)


def _face(rect: QRectF, fill: QColor) -> QLinearGradient:
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, fill.lighter(104))
    gradient.setColorAt(1, fill.darker(103))
    return gradient


def _store(key: tuple, pixmap: QPixmap) -> QPixmap:
    if len(_cache) >= CACHE_LIMIT:
        _cache.clear()
    _cache[key] = pixmap
    return pixmap


def _raised_pixmap(rect: QRectF, radius: float, ellipse: bool, depth: float,
                   fill: QColor, dpr: float) -> QPixmap:
    room = margin(depth)
    size = QSize(math.ceil(rect.width()) + room * 2, math.ceil(rect.height()) + room * 2)
    pixmap = QPixmap(int(size.width() * dpr), int(size.height() * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    face = QRectF(room, room, rect.width(), rect.height())
    offset, blur = OFFSET * depth, BLUR * depth
    _cast_outer(painter, face, radius, ellipse, QColor(theme.SHADOW_DARK), offset, offset, blur)
    _cast_outer(painter, face, radius, ellipse, QColor(theme.SHADOW_LIGHT), -offset, -offset, blur)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_face(face, fill))
    painter.drawPath(_shape(face, radius, ellipse))
    painter.end()
    return pixmap


def paint_raised(painter: QPainter, rect: QRectF, radius: float, ellipse: bool = False,
                 depth: float = 1.0, fill: str | None = None, dpr: float = 1.0) -> None:
    """Draw a shape pressed out of the surface. `rect` is the shape; its
    shadow spreads margin(depth) beyond it."""
    color = fill or theme.SURFACE
    key = _key("raised", rect, radius, ellipse, depth, color, dpr)
    pixmap = _cache.get(key) or _store(
        key, _raised_pixmap(rect, radius, ellipse, depth, QColor(color), dpr)
    )
    room = margin(depth)
    painter.drawPixmap(QPointF(rect.left() - room, rect.top() - room), pixmap)


def _inset_pixmap(rect: QRectF, radius: float, ellipse: bool, depth: float,
                  fill: QColor, dpr: float) -> QPixmap:
    pixmap = QPixmap(int(math.ceil(rect.width()) * dpr), int(math.ceil(rect.height()) * dpr))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    face = QRectF(0, 0, rect.width(), rect.height())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawPath(_shape(face, radius, ellipse))
    offset, blur = OFFSET * depth, BLUR * depth
    _cast_inner(painter, face, radius, ellipse, QColor(theme.SHADOW_DARK), offset, offset, blur)
    _cast_inner(painter, face, radius, ellipse, QColor(theme.SHADOW_LIGHT), -offset, -offset, blur)
    painter.end()
    return pixmap


def paint_inset(painter: QPainter, rect: QRectF, radius: float, ellipse: bool = False,
                depth: float = 1.0, fill: str | None = None, dpr: float = 1.0) -> None:
    """Draw a shape pressed into the surface, such as a track or a pressed button."""
    color = fill or theme.TRACK
    key = _key("inset", rect, radius, ellipse, depth, color, dpr)
    pixmap = _cache.get(key) or _store(
        key, _inset_pixmap(rect, radius, ellipse, depth, QColor(color), dpr)
    )
    painter.drawPixmap(QPointF(rect.left(), rect.top()), pixmap)


class SoftFrame(QFrame):
    """A card: raised in the Soft style, and styled by the stylesheet otherwise."""

    def __init__(self, name: str, radius: float = CARD_RADIUS, depth: float = 1.0,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self._radius = radius
        self._depth = depth
        self._base_margins = None  # the layout's own margins, before any shadow room
        self.apply_style()

    def apply_style(self) -> None:
        """Leave room around the content for the shadow in the Soft style.

        The room is added to the layout's margins (remembering the original
        ones), not to the widget's, so the Classic style gets back exactly what
        its stylesheet gave it.
        """
        layout = self.layout()
        if layout is not None:
            if self._base_margins is None:
                self._base_margins = layout.contentsMargins()
            base = self._base_margins
            room = margin(self._depth) if theme.is_soft() else 0
            layout.setContentsMargins(
                base.left() + room, base.top() + room, base.right() + room, base.bottom() + room
            )
        self.update()

    def paintEvent(self, event) -> None:
        if not theme.is_soft():
            super().paintEvent(event)
            return
        room = margin(self._depth)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        face = QRectF(self.rect()).adjusted(room, room, -room, -room)
        paint_raised(painter, face, self._radius, depth=self._depth,
                     dpr=self.devicePixelRatioF())


class SoftButton(QPushButton):
    """A push button that is a soft raised pill in the Soft style, pressed in
    while it is held down or checked."""

    DEPTH = 0.55

    def _room(self) -> int:
        return margin(self.DEPTH) if theme.is_soft() else 0

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        room = self._room()
        return QSize(size.width() + room * 2, size.height() + room * 2)

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        room = self._room()
        return QSize(size.width() + room * 2, size.height() + room * 2)

    def apply_style(self) -> None:
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:
        if not theme.is_soft():
            super().paintEvent(event)
            return
        room = margin(self.DEPTH)
        face = QRectF(self.rect()).adjusted(room, room, -room, -room)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        name = self.objectName()
        radius = face.height() / 2 if name in ("pill", "primaryButton") else 12
        dpr = self.devicePixelRatioF()
        pressed = (self.isDown() or self.isChecked()) and self.isEnabled()
        if name == "primaryButton" and self.isEnabled():
            if pressed:
                paint_inset(painter, face, radius, depth=self.DEPTH, fill=theme.ACCENT, dpr=dpr)
            else:
                paint_raised(painter, face, radius, depth=self.DEPTH, fill=theme.ACCENT, dpr=dpr)
        elif pressed:
            paint_inset(painter, face, radius, depth=self.DEPTH, dpr=dpr)
        else:
            paint_raised(painter, face, radius, depth=self.DEPTH, dpr=dpr)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = face.toRect()
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel, option, painter, self)


def refresh_all() -> None:
    """After a style change: new margins and sizes for every soft widget."""
    clear_cache()
    for top in QApplication.topLevelWidgets():
        for widget in top.findChildren(QWidget):
            apply = getattr(widget, "apply_style", None)
            if callable(apply):
                apply()
        top.update()
