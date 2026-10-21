# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QWidget

DARK, LIGHT, MATCH_WINDOWS = "dark", "light", "system"

PALETTES: dict[str, dict[str, str]] = {
    DARK: {
        "BACKGROUND": "#0b1220",
        "SURFACE": "#111c2e",
        "SURFACE_RAISED": "#17263b",
        "BORDER": "#203049",
        "CONTROL_BORDER": "#2c405d",
        "TRACK": "#1f2d44",
        "MUTED": "#8ea0b7",
        "DISABLED": "#4d5d73",
        "TEXT": "#e7eef8",
        "HOVER": "#20344f",
        "PRESSED": "#1a2b43",
        "SWITCH_OFF": "#2c405d",
        "ON_ACCENT": "#04121f",
        "ACCENT_HOVER": "#5ccbfa",
        # Base color of see-through hover and stripe fills, as "r, g, b".
        "OVERLAY": "255, 255, 255",
        "ACCENT": "#38bdf8",
        "GREEN": "#34d399",
        "AMBER": "#fbbf24",
        "RED": "#fb7185",
        "VIOLET": "#a78bfa",
        "ORANGE": "#fb923c",
        "PINK": "#f472b6",
        "LIME": "#a3e635",
    },
    LIGHT: {
        "BACKGROUND": "#f3f6fa",
        "SURFACE": "#ffffff",
        "SURFACE_RAISED": "#eef2f7",
        "BORDER": "#dce3ec",
        "CONTROL_BORDER": "#c5d0de",
        "TRACK": "#e2e8f0",
        "MUTED": "#5b6b80",
        "DISABLED": "#a3afbf",
        "TEXT": "#0f1b2d",
        "HOVER": "#e2e8f0",
        "PRESSED": "#d4dce7",
        "SWITCH_OFF": "#c3cedb",
        "ON_ACCENT": "#ffffff",
        "ACCENT_HOVER": "#0369a1",
        "OVERLAY": "15, 23, 42",
        # Deeper accents so text and thin lines stay readable on white.
        "ACCENT": "#0284c7",
        "GREEN": "#059669",
        "AMBER": "#d97706",
        "RED": "#e11d48",
        "VIOLET": "#7c3aed",
        "ORANGE": "#ea580c",
        "PINK": "#db2777",
        "LIME": "#65a30d",
    },
}
THEME_CHOICES = ((DARK, "Dark"), (LIGHT, "Light"), (MATCH_WINDOWS, "Match Windows"))

# The current colors, as module attributes. Code that should follow a theme
# change reads them as theme.TEXT (or theme.color("TEXT")) when it paints,
# rather than importing the names, which would keep the starting values.
BACKGROUND = SURFACE = SURFACE_RAISED = BORDER = CONTROL_BORDER = TRACK = ""
MUTED = DISABLED = TEXT = HOVER = PRESSED = SWITCH_OFF = ON_ACCENT = ""
ACCENT_HOVER = OVERLAY = ""
ACCENT = GREEN = AMBER = RED = VIOLET = ORANGE = PINK = LIME = ""
globals().update(PALETTES[DARK])
current = DARK

ASSETS = Path(__file__).resolve().parent / "assets"

# Segoe Fluent Icons (Windows 11) and Segoe MDL2 Assets (Windows 10) share codes.
GLYPH_SETTINGS = ""
GLYPH_COMPACT = ""
GLYPH_EXPAND = ""


def color(name: str) -> str:
    """A color of the current theme by name, such as "ACCENT"."""
    return PALETTES[current][name]


def resolve(mode: str) -> str:
    """DARK or LIGHT for a theme setting, asking Windows for MATCH_WINDOWS."""
    if mode in PALETTES:
        return mode
    scheme = QGuiApplication.styleHints().colorScheme()
    return LIGHT if scheme == Qt.ColorScheme.Light else DARK


def level_color(percent: float | None, normal: str) -> str:
    if percent is None:
        return MUTED
    if percent >= 90:
        return RED
    if percent >= 75:
        return AMBER
    return normal


def level_text(percent: float | None) -> str:
    if percent is None:
        return "Unavailable"
    if percent >= 90:
        return "High"
    if percent >= 75:
        return "Busy"
    return "Normal"


def glyph_icon(glyph: str, color: str | None = None, size: int = 32) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont()
    font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
    font.setPixelSize(int(size * 0.75))
    painter.setFont(font)
    painter.setPen(QColor(color or TEXT))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pixmap)


def make_app_icon() -> QIcon:
    icon_file = ASSETS / "app_icon.ico"
    if icon_file.exists():
        icon = QIcon(str(icon_file))
        if not icon.isNull():
            return icon
    return _draw_fallback_icon()


def _draw_fallback_icon() -> QIcon:
    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0, QColor(PALETTES[DARK]["ACCENT"]))
    gradient.setColorAt(1, QColor(PALETTES[DARK]["VIOLET"]))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(8, 8, size - 16, size - 16), 56, 56)

    pulse = QPainterPath(QPointF(44, 136))
    for x, y in ((92, 136), (116, 80), (146, 184), (170, 116), (212, 116)):
        pulse.lineTo(x, y)
    pen = QPen(QColor("#ffffff"), 18)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(pulse)
    painter.end()
    return QIcon(pixmap)


def stylesheet() -> str:
    return f"""
QFrame#card, QFrame#compactIndicator {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px;
}}
QFrame#settingsGroup {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
}}
QFrame#divider {{ background: {BORDER}; border: none; }}
QLabel#appTitle {{ font-size: 20px; font-weight: 600; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 11px; font-weight: 600; }}
QLabel#sectionTitle {{ color: {ACCENT}; font-size: 11px; font-weight: 600; }}
QLabel#primary {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#small {{ color: {MUTED}; font-size: 11px; }}
QLabel#bigValue {{ font-size: 22px; font-weight: 600; }}
QLabel#compactValue {{ font-size: 20px; font-weight: 600; }}
QLabel#chip {{
    border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600;
}}
QLabel#error {{ color: {RED}; font-size: 12px; }}
QPushButton#pill {{
    color: {MUTED}; background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER};
    border-radius: 14px; padding: 5px 12px;
}}
QPushButton#pill:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QPushButton#pill:disabled {{ color: {DISABLED}; border-color: {BORDER}; }}
QPushButton {{
    color: {TEXT}; background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER};
    border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ background: {HOVER}; }}
QPushButton:pressed {{ background: {PRESSED}; }}
QPushButton:disabled {{ color: {DISABLED}; }}
QPushButton#iconButton {{ padding: 7px 9px; }}
QPushButton#primaryButton {{
    color: {ON_ACCENT}; background: {ACCENT}; border: none; font-weight: 600;
    padding: 8px 22px;
}}
QPushButton#primaryButton:hover {{ background: {ACCENT_HOVER}; }}
QTableWidget {{
    background: transparent; border: none;
    alternate-background-color: rgba({OVERLAY}, 8);
}}
QHeaderView::section {{
    background: transparent; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 6px 8px;
    font-size: 11px; font-weight: 600;
}}
QComboBox {{
    color: {TEXT}; background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER};
    border-radius: 7px; padding: 5px 10px; min-width: 110px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox:disabled {{ color: {DISABLED}; }}
QComboBox QAbstractItemView {{
    color: {TEXT}; background: {SURFACE}; border: 1px solid {BORDER};
    selection-background-color: {HOVER}; selection-color: {TEXT};
}}
QScrollArea {{ border: none; }}
QListWidget {{
    color: {TEXT}; background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER};
    border-radius: 8px; padding: 4px; outline: none;
}}
QListWidget::item {{ padding: 4px 6px; border-radius: 6px; min-height: 20px; }}
QListWidget::item:selected {{ background: rgba(56, 189, 248, 45); color: {TEXT}; }}
QListWidget::item:hover {{ background: rgba({OVERLAY}, 10); }}
QToolTip {{
    color: {TEXT}; background: {SURFACE_RAISED}; border: 1px solid {CONTROL_BORDER};
    padding: 6px;
}}
QMenu {{ color: {TEXT}; background: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 28px; border-radius: 6px; }}
QMenu::item:selected {{ background: {HOVER}; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
"""


def apply_theme(app: QApplication, mode: str = DARK) -> str:
    """Switch every window to a theme setting; returns DARK or LIGHT."""
    global current
    current = resolve(mode)
    globals().update(PALETTES[current])

    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: SURFACE_RAISED,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE_RAISED,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: ON_ACCENT,
        QPalette.ColorRole.ToolTipBase: SURFACE_RAISED,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.PlaceholderText: MUTED,
        QPalette.ColorRole.Link: ACCENT,
    }
    for role, value in colors.items():
        palette.setColor(role, QColor(value))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(DISABLED))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(stylesheet())
    for widget in app.topLevelWidgets():
        match_title_bar(widget)
    return current


def match_title_bar(widget: QWidget) -> None:
    """Give a window's title bar the theme's dark or light look (Windows 10 2004+)."""
    if sys.platform != "win32" or not widget.isWindow() or not widget.testAttribute(
        Qt.WidgetAttribute.WA_WState_Created
    ):
        return
    dwmwa_use_immersive_dark_mode = 20
    value = ctypes.c_int(1 if current == DARK else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(int(widget.winId())),
        dwmwa_use_immersive_dark_mode,
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
