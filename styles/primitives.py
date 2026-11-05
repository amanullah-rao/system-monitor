# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Drawing helpers shared by the styles: shadows, glows, shapes and color mixing.

Qt gives a widget only one shadow, so the soft ones are drawn by hand: layers
of slightly larger shapes whose transparency builds up into a gradient. They
are drawn into pixmaps that the styles cache per size.
"""

import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

import theme

# Shadow size of a Soft card at full "depth"; smaller things use a fraction of it.
OFFSET = 4.0
BLUR = 8.0
LAYERS = 8
CACHE_LIMIT = 160

_cache: dict[tuple, QPixmap] = {}


def clear_cache() -> None:
    _cache.clear()


def cache_get(key: tuple) -> QPixmap | None:
    return _cache.get(key)


def cache_put(key: tuple, pixmap: QPixmap) -> QPixmap:
    if len(_cache) >= CACHE_LIMIT:
        _cache.clear()
    _cache[key] = pixmap
    return pixmap


def margin(depth: float = 1.0) -> int:
    """Room a Soft raised shape's shadow needs around it."""
    return math.ceil((OFFSET + BLUR) * depth) + 1


# -- colors -----------------------------------------------------------------


def mix(first, second, amount: float) -> QColor:
    """A color between two (0 gives the first, 1 the second), alpha included."""
    a, b = QColor(first), QColor(second)
    t = max(0.0, min(1.0, amount))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def with_alpha(color, alpha: float) -> QColor:
    """The color with an opacity from 0 to 1."""
    result = QColor(color)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


# -- shapes -----------------------------------------------------------------


def shape(rect: QRectF, radius: float, ellipse: bool = False, grow: float = 0.0) -> QPainterPath:
    path = QPainterPath()
    box = rect.adjusted(-grow, -grow, grow, grow)
    if ellipse:
        path.addEllipse(box)
    else:
        path.addRoundedRect(box, max(0.0, radius + grow), max(0.0, radius + grow))
    return path


def chamfered(rect: QRectF, cut: float, corners: str = "tl,br") -> QPainterPath:
    """A rectangle with some corners cut off diagonally ("tl", "tr", "br", "bl")."""
    x1, y1, x2, y2 = rect.left(), rect.top(), rect.right(), rect.bottom()
    chosen = corners.split(",")
    points: list[tuple[float, float]] = []
    points += [(x1, y1 + cut), (x1 + cut, y1)] if "tl" in chosen else [(x1, y1)]
    points += [(x2 - cut, y1), (x2, y1 + cut)] if "tr" in chosen else [(x2, y1)]
    points += [(x2, y2 - cut), (x2 - cut, y2)] if "br" in chosen else [(x2, y2)]
    points += [(x1 + cut, y2), (x1, y2 - cut)] if "bl" in chosen else [(x1, y2)]
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    path.closeSubpath()
    return path


# -- shadows and glows -------------------------------------------------------


def _intensity(grow: float, blur: float) -> float:
    return (1 - grow / blur) ** 2


def cast_shadow(
    painter: QPainter, rect: QRectF, radius: float, ellipse: bool, color: QColor,
    dx: float, dy: float, blur: float,
) -> None:
    """A soft shadow around the shape, moved by (dx, dy). The color's alpha is
    the shadow's strongest opacity, right at the shape's edge."""
    base = color.alphaF()
    painter.setPen(Qt.PenStyle.NoPen)
    for layer in range(LAYERS):
        grow = blur * (LAYERS - layer) / LAYERS
        inner = blur * (LAYERS - layer - 1) / LAYERS
        alpha = base * (_intensity(inner, blur) - _intensity(grow, blur))
        shade = QColor(color)
        shade.setAlphaF(max(0.0, min(1.0, alpha)))
        painter.setBrush(shade)
        painter.drawPath(shape(rect.translated(dx, dy), radius, ellipse, grow))


def cast_inner_shadow(
    painter: QPainter, rect: QRectF, radius: float, ellipse: bool, color: QColor,
    dx: float, dy: float, blur: float,
) -> None:
    """A soft shadow just inside the shape, falling from (dx, dy)."""
    painter.save()
    painter.setClipPath(shape(rect, radius, ellipse))
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
        hole = shape(rect.translated(dx, dy), radius, ellipse, -shrink)
        painter.fillPath(wide.subtracted(hole), shade)
    painter.restore()


def glow_path(
    painter: QPainter, path: QPainterPath, color: QColor, core: float = 1.2,
    spread: float = 7.0, strength: float = 0.55,
) -> None:
    """Outline a path with a neon glow: a bright thin line inside wider, fainter ones."""
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for layer in range(LAYERS, 0, -1):
        pen = QPen(with_alpha(color, strength * (1 - layer / (LAYERS + 1)) ** 2 * 0.45),
                   core + spread * layer / LAYERS)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
    pen = QPen(color, core)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(path)


# -- soft (neumorphic) shapes, cached ----------------------------------------


def _key(kind: str, rect: QRectF, radius: float, ellipse: bool, depth: float,
         fill: str, dpr: float) -> tuple:
    return (kind, round(rect.width()), round(rect.height()), round(radius, 1), ellipse,
            depth, fill, theme.current, theme.current_style, dpr)


def _face(rect: QRectF, fill: QColor) -> QLinearGradient:
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0, fill.lighter(104))
    gradient.setColorAt(1, fill.darker(103))
    return gradient


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
    cast_shadow(painter, face, radius, ellipse, QColor(theme.SHADOW_DARK), offset, offset, blur)
    cast_shadow(painter, face, radius, ellipse, QColor(theme.SHADOW_LIGHT), -offset, -offset, blur)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_face(face, fill))
    painter.drawPath(shape(face, radius, ellipse))
    painter.end()
    return pixmap


def paint_raised(painter: QPainter, rect: QRectF, radius: float, ellipse: bool = False,
                 depth: float = 1.0, fill: str | None = None, dpr: float = 1.0) -> None:
    """Draw a shape pressed out of the surface. `rect` is the shape; its
    shadow spreads margin(depth) beyond it."""
    color = fill or theme.SURFACE
    key = _key("raised", rect, radius, ellipse, depth, color, dpr)
    pixmap = cache_get(key) or cache_put(
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
    painter.drawPath(shape(face, radius, ellipse))
    offset, blur = OFFSET * depth, BLUR * depth
    cast_inner_shadow(painter, face, radius, ellipse, QColor(theme.SHADOW_DARK), offset, offset, blur)
    cast_inner_shadow(painter, face, radius, ellipse, QColor(theme.SHADOW_LIGHT), -offset, -offset, blur)
    painter.end()
    return pixmap


def paint_inset(painter: QPainter, rect: QRectF, radius: float, ellipse: bool = False,
                depth: float = 1.0, fill: str | None = None, dpr: float = 1.0) -> None:
    """Draw a shape pressed into the surface, such as a track or a pressed button."""
    color = fill or theme.TRACK
    key = _key("inset", rect, radius, ellipse, depth, color, dpr)
    pixmap = cache_get(key) or cache_put(
        key, _inset_pixmap(rect, radius, ellipse, depth, QColor(color), dpr)
    )
    painter.drawPixmap(QPointF(rect.left(), rect.top()), pixmap)
