# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Widgets that look the way the active style says."""

from PySide6.QtCore import QRectF, QSize, QVariantAnimation
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QStyle, QStyleOptionButton, QWidget

import theme

from . import primitives
from .registry import current

HOVER_MS = 140


class StyledFrame(QFrame):
    """A card. Styles that draw their own cards paint it; Classic leaves it to
    the stylesheet. `kind` is "card" (dashboard), "compact", "group"
    (settings) or "panel" (the hover details)."""

    def __init__(self, name: str, kind: str = "card", accent_name: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(name)
        self.kind = kind
        # A theme color name, such as "GREEN", for styles that tint cards.
        self.accent_name = accent_name
        self._base_margins = None  # the layout's own margins, before any shadow room
        self.apply_style()

    def apply_style(self) -> None:
        """Leave room around the content for the style's shadow or glow.

        The room is added to the layout's margins (remembering the original
        ones), not to the widget's, so Classic gets back exactly what its
        stylesheet gave it.
        """
        layout = self.layout()
        if layout is not None:
            if self._base_margins is None:
                self._base_margins = layout.contentsMargins()
            base = self._base_margins
            style = current()
            room = style.card_room(self.kind) if style.custom_painting else 0
            layout.setContentsMargins(
                base.left() + room, base.top() + room, base.right() + room, base.bottom() + room
            )
        self.update()

    def paintEvent(self, event) -> None:
        style = current()
        if not style.custom_painting:
            super().paintEvent(event)
            return
        room = style.card_room(self.kind)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        face = QRectF(self.rect()).adjusted(room, room, -room, -room)
        accent = theme.color(self.accent_name) if self.accent_name else None
        style.paint_card(painter, face, self.kind, accent, self.devicePixelRatioF())


class StyledButton(QPushButton):
    """A push button drawn by the active style: it can be raised, glossy,
    outlined, … and fades into its hover color. The stylesheet gives it the
    text color, padding and font."""

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self._hover = 0.0
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(HOVER_MS)
        self._fade.valueChanged.connect(self._set_hover)

    def _room(self) -> int:
        style = current()
        return style.button_room() if style.custom_painting else 0

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

    def _set_hover(self, value) -> None:
        self._hover = float(value)
        self.update()

    def _fade_to(self, target: float) -> None:
        if not current().hover_animation:
            self._hover = target
            return
        self._fade.stop()
        self._fade.setStartValue(self._hover)
        self._fade.setEndValue(target)
        self._fade.start()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._fade_to(1.0)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._fade_to(0.0)

    def paintEvent(self, event) -> None:
        style = current()
        if not style.custom_painting:
            super().paintEvent(event)
            return
        room = style.button_room()
        face = QRectF(self.rect()).adjusted(room, room, -room, -room)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        enabled = self.isEnabled()
        style.paint_button(
            painter, face, self.objectName(), self.isDown() and enabled,
            self._hover if enabled else 0.0, enabled, self.isChecked(), self.devicePixelRatioF(),
        )
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = face.toRect()
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel, option, painter, self)


def refresh_all() -> None:
    """After a style change: new margins, sizes and cached drawings everywhere."""
    primitives.clear_cache()
    for top in QApplication.topLevelWidgets():
        for widget in top.findChildren(QWidget):
            apply = getattr(widget, "apply_style", None)
            if callable(apply):
                apply()
        top.update()
