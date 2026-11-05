# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import os
import sys
from collections.abc import Callable
from html import escape

from PySide6.QtCore import QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import app_info
import dialogs
import diagnostics
import i18n
import styles
import theme
from i18n import N_, tr
from metrics import (
    METRICS,
    STRIP_PRESETS,
    TRAY_ICON_CHOICES,
    MetricValue,
    in_order,
    preview_values,
)
from settings import (
    ALERT_BATTERY_PERCENT,
    ALERT_CPU_PERCENT,
    ALERT_DRIVE_FREE_PERCENT,
    ALERT_RAM_PERCENT,
    ALERTS_ENABLED,
    CLOSE_TO_TRAY,
    DATA_LIMIT_GB,
    LANGUAGE,
    MANAGE_SENSOR_APP,
    NETWORK_ADAPTER,
    REFRESH_SECONDS,
    SPEED_UNIT,
    START_MINIMIZED,
    STYLE,
    STRIP_BACKGROUND_OPACITY,
    STRIP_COLORED,
    STRIP_FONT_FAMILY,
    STRIP_FONT_SIZE,
    STRIP_HIDE_FULL_SCREEN,
    STRIP_HOVER_PANEL,
    STRIP_ITEMS,
    STRIP_ROWS,
    STRIP_SCREEN,
    STRIP_VISIBLE,
    TEMPERATURE_UNIT,
    THEME,
    TRAY_ICON,
    AppSettings,
    autostart_supported,
    is_autostart_enabled,
    set_autostart,
)
from system_monitor import network_adapters
from taskbar_strip import (
    columns_width,
    find_taskbars,
    layout_columns,
    list_monitors,
    paint_columns,
    screen_device_name,
    strip_font,
)
from styles import StyledButton, StyledFrame
from theme import THEME_CHOICES, make_app_icon, match_title_bar
from updates import (
    CURRENT,
    NEWER,
    NO_RELEASES,
    ReleaseInfo,
    UpdateChecker,
    UpdateDownloader,
)

# Choice labels are English and marked with N_; they go through tr() when shown.
REFRESH_CHOICES = (
    (0.5, N_("Every ½ second")),
    (1.0, N_("Every second")),
    (2.0, N_("Every 2 seconds")),
    (5.0, N_("Every 5 seconds")),
)
ROW_CHOICES = ((2, N_("Two lines (stacked)")), (1, N_("One line")))
FONT_SIZE_CHOICES = (
    (8.0, N_("Small")),
    (9.0, N_("Default")),
    (10.0, N_("Large")),
    (11.0, N_("Extra large")),
)
BACKGROUND_CHOICES = (
    (0, N_("None")),
    (25, N_("Subtle")),
    (50, N_("Medium")),
    (75, N_("Strong")),
)
TEMPERATURE_CHOICES = (("C", N_("Celsius (°C)")), ("F", N_("Fahrenheit (°F)")))
SPEED_CHOICES = (
    ("bytes", N_("Bytes per second (KB/s, MB/s)")),
    ("bits", N_("Bits per second (Kbps, Mbps)")),
)
# Fonts offered for the taskbar strip, when they're installed.
STRIP_FONTS = (
    "Segoe UI",
    "Segoe UI Variable Text",
    "Calibri",
    "Arial",
    "Tahoma",
    "Verdana",
    "Consolas",
    "Cascadia Mono",
    "Malgun Gothic",
)
COLOR_CHOICES = (
    (N_("White"), "#ffffff"),
    (N_("Red"), "#f87171"),
    (N_("Orange"), "#fb923c"),
    (N_("Yellow"), "#facc15"),
    (N_("Green"), "#4ade80"),
    (N_("Cyan"), "#22d3ee"),
    (N_("Blue"), "#60a5fa"),
    (N_("Violet"), "#a78bfa"),
    (N_("Pink"), "#f472b6"),
)


def screen_choices() -> list[tuple[str, str]]:
    """(device name, label) for the screen picker; "" follows the main screen."""
    primary = QGuiApplication.primaryScreen()
    monitors = list_monitors()
    taskbars = find_taskbars(monitors)
    choices = [("", tr("Main screen"))]
    for number, screen in enumerate(QGuiApplication.screens(), start=1):
        device = screen_device_name(screen, monitors)
        size = screen.geometry().size() * screen.devicePixelRatio()
        label = tr("Screen {number}: {name} ({width}×{height})").format(
            number=number,
            name=screen.model() or device,
            width=size.width(),
            height=size.height(),
        )
        if screen == primary:
            label += " · " + tr("main")
        if taskbars and device not in taskbars:
            label += " · " + tr("no taskbar")
        choices.append((device, label))
    return choices


def adapter_choices(saved: str) -> list[tuple[str, str]]:
    """(adapter name, label) for the network picker; "" measures all of them."""
    choices = [("", tr("All adapters"))]
    adapters = network_adapters()
    for name, connected in adapters:
        choices.append(
            (name, name if connected else tr("{name} (not connected)").format(name=name))
        )
    if saved and saved not in {name for name, _ in adapters}:
        choices.append((saved, tr("{name} (not found)").format(name=saved)))
    return choices


def strip_font_choices() -> list[tuple[str, str]]:
    installed = set(QFontDatabase.families())
    families = [family for family in STRIP_FONTS if family in installed]
    return [(family, family) for family in families] or [("Segoe UI", "Segoe UI")]


def fill_combo(combo: QComboBox, choices, current) -> None:
    """Replace a combo box's items without emitting change signals."""
    combo.blockSignals(True)
    combo.clear()
    for value, label in choices:
        combo.addItem(label, value)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    combo.blockSignals(False)


def translated(choices) -> list[tuple[object, str]]:
    return [(value, tr(label)) for value, label in choices]


class NoWheelComboBox(QComboBox):
    """A combo box that leaves the mouse wheel to the page.

    Otherwise scrolling the Settings page changes whichever choice happens
    to pass under the pointer. Click it (or use the keyboard) to change it.
    """

    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """The same for number boxes."""

    def wheelEvent(self, event) -> None:
        event.ignore()


def percent_box(minimum: int, maximum: int, suffix: str = " %") -> NoWheelSpinBox:
    box = NoWheelSpinBox()
    box.setRange(minimum, maximum)
    box.setSuffix(suffix)
    box.setMinimumWidth(96)
    return box


class ToggleSwitch(QAbstractButton):
    """An on/off switch, drawn by the active style, whose knob slides."""

    SLIDE_MS = 130

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._progress = 0.0  # 0 off .. 1 on
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(self.SLIDE_MS)
        self._slide.valueChanged.connect(self._set_progress)
        self.toggled.connect(self._animate)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return styles.current().toggle_size()

    def apply_style(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.update()

    def _set_progress(self, value) -> None:
        self._progress = float(value)
        self.update()

    def _animate(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        if not self.isVisible():
            self._progress = target
            return
        self._slide.stop()
        self._slide.setStartValue(self._progress)
        self._slide.setEndValue(target)
        self._slide.start()

    def paintEvent(self, event) -> None:
        del event
        target = 1.0 if self.isChecked() else 0.0
        # Changes made in code (without a click) jump straight to the new state.
        if self._slide.state() != QVariantAnimation.State.Running:
            self._progress = target
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        styles.current().paint_toggle(
            painter, QRectF(self.rect()), self._progress, self.isEnabled(),
            self.devicePixelRatioF(),
        )


class SettingRow(QWidget):
    def __init__(self, title: str, description: str, control: QWidget) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("primary")
        self.description = QLabel(description)
        self.description.setObjectName("small")
        self.description.setWordWrap(True)
        text.addWidget(self.title)
        text.addWidget(self.description)
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


class StripPreview(QWidget):
    """The taskbar strip drawn with sample values, using the strip's own painter."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._font = strip_font()
        self._columns = []
        self._colors: dict[str, str] = {}
        self.setFixedHeight(48)

    def set_layout(
        self,
        keys: list[str],
        rows: int,
        font_size: float,
        font_family: str = "Segoe UI",
        colors: dict[str, str] | None = None,
    ) -> None:
        self._font = strip_font(font_size, font_family)
        self._colors = colors or {}
        self._columns = layout_columns(in_order(keys), rows, QFontMetrics(self._font))
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(theme.CONTROL_BORDER))
        # Drawn like a dark Windows taskbar whatever the app's theme.
        painter.setBrush(QColor("#1c1c1c"))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        # Right-aligned like the real strip, which sits next to the clock.
        offset = max(0, self.width() - columns_width(self._columns) - 8)
        painter.translate(offset, 0)
        values = {key: MetricValue(text) for key, text in preview_values().items()}
        paint_columns(
            painter, self.height(), self._columns, values, False, False, self._font,
            self._colors,
        )


def swatch(color: str | None) -> QIcon:
    """A small colored square for a menu or list entry."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor(theme.CONTROL_BORDER))
    painter.setBrush(QColor(color) if color else Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(QRectF(1.5, 1.5, 13, 13), 3, 3)
    painter.end()
    return QIcon(pixmap)


class StripLayoutEditor(QWidget):
    """Choose, order, color and group what the taskbar strip shows."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(6)

        heading = QLabel(tr("Layout and order"))
        heading.setObjectName("primary")
        note = QLabel(
            tr(
                "Tick what to show and use the arrows (or drag) to set the order. "
                "With two lines, each pair in the list shares a column."
            )
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addSpacing(4)

        self.preview = StripPreview()
        layout.addWidget(self.preview)
        layout.addSpacing(6)

        presets_label = QLabel(tr("Quick presets"))
        presets_label.setObjectName("small")
        layout.addWidget(presets_label)
        presets = QGridLayout()
        presets.setHorizontalSpacing(8)
        presets.setVerticalSpacing(8)
        for index, (name, keys) in enumerate(STRIP_PRESETS):
            button = StyledButton(tr(name))
            button.setObjectName("pill")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, keys=keys: self._apply_preset(keys))
            presets.addWidget(button, index // 3, index % 3)
        layout.addLayout(presets)
        layout.addSpacing(8)

        editor = QHBoxLayout()
        editor.setSpacing(10)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setFixedHeight(len(METRICS) * 30 + 10)
        self.list.itemChanged.connect(self._save)
        self.list.model().rowsMoved.connect(self._save)
        buttons = QVBoxLayout()
        buttons.setSpacing(8)
        up = StyledButton("▲  " + tr("Move up"))
        down = StyledButton("▼  " + tr("Move down"))
        self._color_button = StyledButton(tr("Text color…"))
        self._color_button.setToolTip(tr("Pick a color for the selected reading"))
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        self._color_button.clicked.connect(self._pick_color)
        buttons.addWidget(up)
        buttons.addWidget(down)
        buttons.addWidget(self._color_button)
        buttons.addStretch(1)
        editor.addWidget(self.list, 1)
        editor.addLayout(buttons)
        layout.addLayout(editor)
        layout.addSpacing(6)

        rows_line = QHBoxLayout()
        rows_label = QLabel(tr("Lines"))
        rows_label.setObjectName("primary")
        self.rows = NoWheelComboBox()
        for rows, label in ROW_CHOICES:
            self.rows.addItem(tr(label), rows)
        self.rows.currentIndexChanged.connect(
            lambda: self._settings.set_value(STRIP_ROWS, self.rows.currentData())
        )
        rows_line.addWidget(rows_label)
        rows_line.addStretch(1)
        rows_line.addWidget(self.rows)
        layout.addLayout(rows_line)

    def _checked_keys(self) -> list[str]:
        keys = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                keys.append(item.data(Qt.ItemDataRole.UserRole))
        return keys

    def _refresh_preview(self, keys: list[str]) -> None:
        self.preview.set_layout(
            keys,
            self._settings.value(STRIP_ROWS),
            self._settings.value(STRIP_FONT_SIZE),
            self._settings.value(STRIP_FONT_FAMILY),
            self._settings.colors(),
        )

    def sync(self) -> None:
        saved = [metric.key for metric in in_order(self._settings.keys(STRIP_ITEMS))]
        rows = self._settings.value(STRIP_ROWS)
        colors = self._settings.colors()
        # Rebuild only when the list disagrees, so an unticked item stays put.
        if self.list.count() != len(METRICS) or self._checked_keys() != saved:
            self.list.blockSignals(True)
            self.list.clear()
            unchecked = [metric for metric in METRICS if metric.key not in saved]
            for metric in in_order(saved) + unchecked:
                item = QListWidgetItem(
                    f"{tr(metric.name)}   ·   "
                    + tr("shows as “{short}”").format(short=metric.short)
                )
                item.setData(Qt.ItemDataRole.UserRole, metric.key)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                item.setCheckState(
                    Qt.CheckState.Checked if metric.key in saved else Qt.CheckState.Unchecked
                )
                self.list.addItem(item)
            self.list.blockSignals(False)
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setIcon(swatch(colors.get(item.data(Qt.ItemDataRole.UserRole))))
        self.rows.blockSignals(True)
        self.rows.setCurrentIndex(max(0, self.rows.findData(rows)))
        self.rows.blockSignals(False)
        self._refresh_preview(saved)

    def _save(self, *_) -> None:
        keys = self._checked_keys()
        if not keys:
            # At least one reading must stay on the strip.
            self.list.clear()
            self.sync()
            return
        self._settings.set_keys(STRIP_ITEMS, keys)
        self._refresh_preview(keys)

    def _move(self, step: int) -> None:
        row = self.list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.list.count():
            return
        self.list.blockSignals(True)
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)
        self.list.blockSignals(False)
        self._save()

    def _pick_color(self) -> None:
        item = self.list.currentItem()
        if item is None:
            dialogs.inform(
                self, tr("Text color"), tr("Select a reading in the list first.")
            )
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        for name, color in COLOR_CHOICES:
            menu.addAction(swatch(color), tr(name)).triggered.connect(
                lambda _=False, color=color: self._set_color(key, color)
            )
        menu.addSeparator()
        menu.addAction(tr("Other color…")).triggered.connect(
            lambda: self._custom_color(key)
        )
        menu.addAction(tr("Default color")).triggered.connect(
            lambda: self._set_color(key, None)
        )
        menu.exec(self._color_button.mapToGlobal(self._color_button.rect().bottomLeft()))

    def _custom_color(self, key: str) -> None:
        current = QColor(self._settings.colors().get(key, "#ffffff"))
        chosen = QColorDialog.getColor(current, self, tr("Text color"))
        if chosen.isValid():
            self._set_color(key, chosen.name())

    def _set_color(self, key: str, color: str | None) -> None:
        colors = self._settings.colors()
        if color is None:
            colors.pop(key, None)
        else:
            colors[key] = color
        self._settings.set_colors(colors)
        self.sync()

    def _apply_preset(self, keys: tuple[str, ...]) -> None:
        self._settings.set_keys(STRIP_ITEMS, list(keys))
        self.list.clear()
        self.sync()


class AboutPanel(QWidget):
    def __init__(
        self, diagnostics: Callable[[], str], run_welcome: Callable[[], None]
    ) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(48, 48))
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)
        name = QLabel(f"{app_info.APP_NAME}  {app_info.VERSION}")
        name.setObjectName("primary")
        description = QLabel(tr(app_info.DESCRIPTION))
        description.setObjectName("small")
        description.setWordWrap(True)
        author = QLabel(tr("Made by {author}").format(author=app_info.AUTHOR))
        author.setObjectName("muted")
        self._links = links = QLabel()
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        # The GPL asks for the copyright, the lack of warranty and the license
        # to be shown in the app.
        self._legal = copyright_label = QLabel()
        copyright_label.setObjectName("small")
        copyright_label.setWordWrap(True)
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        for widget in (name, description, author, links, copyright_label):
            text.addWidget(widget)

        updates = QHBoxLayout()
        updates.setContentsMargins(0, 8, 0, 0)
        updates.setSpacing(12)
        self._check_button = StyledButton(tr("Check for updates"))
        self._check_button.setToolTip(
            tr("Asks GitHub for the latest release. Nothing about this PC is sent.")
        )
        self._check_button.clicked.connect(self._check_for_updates)
        self._update_status = QLabel()
        self._update_status.setObjectName("small")
        self._update_status.setWordWrap(True)
        self._update_status.setOpenExternalLinks(True)
        self._update_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        updates.addWidget(self._check_button)
        updates.addWidget(self._update_status, 1)
        text.addLayout(updates)

        download = QHBoxLayout()
        download.setSpacing(12)
        self._download_button = StyledButton(tr("Download and install"))
        self._download_button.setObjectName("primaryButton")
        self._download_button.setToolTip(
            tr(
                "Downloads the new installer from GitHub, checks its checksum and "
                "opens it. Windows asks for permission before it installs."
            )
        )
        self._download_button.clicked.connect(self._start_download)
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        download.addWidget(self._download_button)
        download.addWidget(self._progress, 1)
        self._download_row = QWidget()
        self._download_row.setLayout(download)
        download.setContentsMargins(0, 0, 0, 0)
        self._download_row.hide()
        text.addWidget(self._download_row)

        report = QHBoxLayout()
        report.setSpacing(12)
        copy_button = StyledButton(tr("Copy diagnostic info"))
        copy_button.setToolTip(
            tr(
                "Copies what System Monitor can and can't read on this PC (hardware and "
                "sensors only), to paste into a problem report."
            )
        )
        copy_button.clicked.connect(self._copy_diagnostics)
        self._copy_status = QLabel()
        self._copy_status.setObjectName("small")
        self._copy_status.setWordWrap(True)
        report.addWidget(copy_button)
        report.addWidget(self._copy_status, 1)
        text.addLayout(report)

        welcome = QHBoxLayout()
        welcome_button = StyledButton(tr("Run the welcome setup again"))
        welcome_button.clicked.connect(run_welcome)
        welcome.addWidget(welcome_button)
        welcome.addStretch(1)
        text.addLayout(welcome)
        layout.addLayout(text, 1)
        self._diagnostics = diagnostics

        self._checker = UpdateChecker(self)
        self._checker.finished.connect(self._show_update_result)
        self._downloader = UpdateDownloader(self)
        self._downloader.progress.connect(self._show_progress)
        self._downloader.downloaded.connect(self._installer_ready)
        self._downloader.failed.connect(self._download_failed)
        self._release: ReleaseInfo | None = None
        self._status_text = ""  # set while a download or its result is shown
        self.apply_theme_colors()

    def apply_theme_colors(self) -> None:
        link_style = f"color: {theme.ACCENT}; text-decoration: none;"
        separator = "&nbsp;&nbsp;·&nbsp;&nbsp;"
        self._links.setText(
            f'<a style="{link_style}" href="{app_info.REPOSITORY_URL}">{tr("Project page")}</a>'
            f"{separator}"
            f'<a style="{link_style}" href="{app_info.ISSUES_URL}">{tr("Report a problem")}</a>'
            f"{separator}"
            f'<a style="{link_style}" href="{app_info.GITHUB_URL}">{tr("GitHub profile")}</a>'
        )
        self._legal.setText(
            tr("{copyright}. Free software under the {license}, with ABSOLUTELY NO WARRANTY.")
            .format(
                copyright=escape(app_info.COPYRIGHT),
                license=f'<a style="{link_style}" href="{app_info.LICENSE_URL}">'
                f"{app_info.LICENSE}</a>",
            )
        )
        if self._release is not None:
            self._show_update_result(self._release)

    def _copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(self._diagnostics())
        self._copy_status.setText(
            tr("Copied. Paste it into a problem report with “Report a problem” above.")
        )

    def _check_for_updates(self) -> None:
        if self._checker.check():
            self._check_button.setEnabled(False)
            self._update_status.setText(tr("Checking…"))

    def _show_update_result(self, info: ReleaseInfo) -> None:
        self._release = info
        self._check_button.setEnabled(True)
        self._download_row.hide()
        link_style = f"color: {theme.ACCENT}; text-decoration: none;"
        if info.state == NEWER:
            text = (
                f'<span style="color:{theme.GREEN}">'
                + tr("Version {version} is available.").format(version=escape(info.version))
                + "</span>"
            )
            if info.can_download:
                self._download_row.show()
                self._download_button.setEnabled(True)
                self._progress.setValue(0)
            else:
                text += (
                    f'&nbsp;&nbsp;<a style="{link_style}" href="{escape(info.link)}">'
                    f'{tr("Download")}</a>'
                )
            self._update_status.setText(self._status_text or text)
        elif info.state == CURRENT:
            self._update_status.setText(
                tr("You have the latest version ({version}).").format(
                    version=app_info.VERSION
                )
            )
        elif info.state == NO_RELEASES:
            self._update_status.setText(tr("No releases have been published yet."))
        else:
            self._update_status.setText(escape(info.message))

    def _start_download(self) -> None:
        if self._release is None or not self._downloader.start(self._release):
            return
        self._download_button.setEnabled(False)
        self._check_button.setEnabled(False)
        self._status_text = tr("Downloading…")
        self._update_status.setText(self._status_text)

    def _show_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(done)
        else:
            self._progress.setRange(0, 0)

    def _installer_ready(self, path: str) -> None:
        self._check_button.setEnabled(True)
        self._status_text = tr(
            "Downloaded and checked. The installer opened; Windows will ask for "
            "permission to continue."
        )
        self._update_status.setText(self._status_text)
        try:
            os.startfile(path)  # noqa: S606 - the verified installer, on Windows
        except OSError as error:
            self._status_text = tr("Couldn't open the installer ({reason}).").format(
                reason=error
            )
            self._update_status.setText(self._status_text)
            self._download_button.setEnabled(True)

    def _download_failed(self, message: str) -> None:
        self._check_button.setEnabled(True)
        self._download_button.setEnabled(True)
        self._progress.setValue(0)
        self._status_text = escape(message)
        self._update_status.setText(self._status_text)


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        tray_available: bool,
        sensor_app_available: bool,
        sensor_app_shows_tray_icon: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._tray_available = tray_available
        self._sensor_app_available = sensor_app_available
        self.setWindowTitle(tr("Settings"))
        self.resize(620, 800)

        self._autostart = ToggleSwitch()
        self._minimized = ToggleSwitch()
        self._sensor_app = ToggleSwitch()
        self._strip = ToggleSwitch()
        self._colored = ToggleSwitch()
        self._hover_panel = ToggleSwitch()
        self._hide_full_screen = ToggleSwitch()
        self._close_to_tray = ToggleSwitch()
        self._alerts = ToggleSwitch()
        self._refresh = NoWheelComboBox()
        for seconds, label in REFRESH_CHOICES:
            self._refresh.addItem(tr(label), seconds)
        self._bound_switches = (
            (self._minimized, START_MINIMIZED),
            (self._sensor_app, MANAGE_SENSOR_APP),
            (self._strip, STRIP_VISIBLE),
            (self._colored, STRIP_COLORED),
            (self._hover_panel, STRIP_HOVER_PANEL),
            (self._hide_full_screen, STRIP_HIDE_FULL_SCREEN),
            (self._close_to_tray, CLOSE_TO_TRAY),
            (self._alerts, ALERTS_ENABLED),
        )
        self._strip_layout = StripLayoutEditor(settings)
        self._tray_icon = NoWheelComboBox()
        for key, label in TRAY_ICON_CHOICES:
            self._tray_icon.addItem(tr(label), key)
        self._font_size = NoWheelComboBox()
        for points, label in FONT_SIZE_CHOICES:
            self._font_size.addItem(tr(label), points)
        self._font_family = NoWheelComboBox()
        self._background = NoWheelComboBox()
        for percent, label in BACKGROUND_CHOICES:
            self._background.addItem(tr(label), percent)
        self._screen = NoWheelComboBox()
        self._adapter = NoWheelComboBox()
        self._adapter.setMinimumWidth(180)
        self._speed_unit = NoWheelComboBox()
        for value, label in SPEED_CHOICES:
            self._speed_unit.addItem(tr(label), value)
        self._data_limit = NoWheelSpinBox()
        self._data_limit.setRange(0, 100_000)
        self._data_limit.setSuffix(" GB")
        self._data_limit.setSpecialValueText(tr("No limit"))
        self._data_limit.setMinimumWidth(110)
        self._theme = NoWheelComboBox()
        for mode, label in THEME_CHOICES:
            self._theme.addItem(tr(label), mode)
        self._language = NoWheelComboBox()
        for code, name in i18n.LANGUAGES:
            self._language.addItem(name, code)
        self._style = NoWheelComboBox()
        for value, label in styles.choices():
            self._style.addItem(tr(label), value)
        self._temperature_unit = NoWheelComboBox()
        for value, label in TEMPERATURE_CHOICES:
            self._temperature_unit.addItem(tr(label), value)
        self._alert_cpu = percent_box(50, 100)
        self._alert_ram = percent_box(50, 100)
        self._alert_drive = percent_box(1, 50)
        self._alert_battery = percent_box(1, 50)
        self._bound_numbers = (
            (self._data_limit, DATA_LIMIT_GB),
            (self._alert_cpu, ALERT_CPU_PERCENT),
            (self._alert_ram, ALERT_RAM_PERCENT),
            (self._alert_drive, ALERT_DRIVE_FREE_PERCENT),
            (self._alert_battery, ALERT_BATTERY_PERCENT),
        )
        # (box, setting) pairs for choice boxes that store their current data.
        self._bound_choices = (
            (self._refresh, REFRESH_SECONDS),
            (self._tray_icon, TRAY_ICON),
            (self._font_size, STRIP_FONT_SIZE),
            (self._font_family, STRIP_FONT_FAMILY),
            (self._background, STRIP_BACKGROUND_OPACITY),
            (self._screen, STRIP_SCREEN),
            (self._adapter, NETWORK_ADAPTER),
            (self._speed_unit, SPEED_UNIT),
            (self._theme, THEME),
            (self._style, STYLE),
            (self._temperature_unit, TEMPERATURE_UNIT),
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 12)
        layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        title = QLabel(tr("Settings"))
        title.setObjectName("appTitle")
        subtitle = QLabel(tr("Changes are saved automatically."))
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._minimized_row = SettingRow(
            tr("Start hidden"),
            tr("When Windows starts the app, keep it in the tray instead of opening the window."),
            self._minimized,
        )
        self._add_group(
            layout,
            tr("STARTUP"),
            (
                SettingRow(
                    tr("Start with Windows"),
                    tr("Open System Monitor automatically when you sign in."),
                    self._autostart,
                ),
                self._minimized_row,
            ),
        )
        self._style_row = SettingRow(tr("Style"), "", self._style)
        self._add_group(
            layout,
            tr("APPEARANCE"),
            (
                SettingRow(
                    tr("Theme"),
                    tr("Dark, light, or follow the app mode set in Windows."),
                    self._theme,
                ),
                self._style_row,
                SettingRow(
                    tr("Language"),
                    tr("The language of the app. It changes after a restart."),
                    self._language,
                ),
                SettingRow(
                    tr("Temperature unit"),
                    tr("How temperatures are shown everywhere in the app."),
                    self._temperature_unit,
                ),
            ),
        )
        if not sensor_app_available:
            sensor_text = (
                tr(
                    "CPU temperature isn't set up on this PC. Run the System Monitor "
                    "installer again and keep “Show CPU temperature” ticked."
                )
                if getattr(sys, "frozen", False)
                else tr(
                    "CPU temperature isn't set up on this PC. Install "
                    "LibreHardwareMonitor, then run sensor_setup.ps1 as administrator."
                )
            )
        elif sensor_app_shows_tray_icon:
            sensor_text = tr(
                "Starts LibreHardwareMonitor with this app and closes it when you quit. "
                "It shows its own tray icon; run sensor_setup.ps1 as administrator "
                "once to read the sensors without it."
            )
        else:
            sensor_text = tr(
                "Reads CPU temperature in the background, with no extra window or "
                "tray icon. Starts with this app and stops when you quit."
            )
        self._sensor_row = SettingRow(
            tr("CPU temperature sensor"), sensor_text, self._sensor_app
        )
        self._add_group(layout, tr("SENSORS"), (self._sensor_row,))
        self._strip_rows = (
            SettingRow(
                tr("Show on the taskbar"),
                tr("Live readings next to the clock. Drag them to move."),
                self._strip,
            ),
            SettingRow(
                tr("Color warnings"),
                tr("Turn a reading amber or red when it gets high."),
                self._colored,
            ),
            SettingRow(
                tr("Details on hover"),
                tr(
                    "Rest the mouse on the readings to see every CPU core, the "
                    "busiest apps and each connection's speed."
                ),
                self._hover_panel,
            ),
            SettingRow(
                tr("Hide during full-screen apps"),
                tr(
                    "Step aside for games, videos and remote desktops such as Parsec, "
                    "like the Windows taskbar does."
                ),
                self._hide_full_screen,
            ),
            SettingRow(
                tr("Text size"),
                tr("Larger text is easier to read; two lines fit up to Extra large."),
                self._font_size,
            ),
            SettingRow(
                tr("Font"),
                tr("The typeface of the readings."),
                self._font_family,
            ),
            SettingRow(
                tr("Background"),
                tr("A dark or light backdrop behind the text, to read it more easily."),
                self._background,
            ),
            SettingRow(
                tr("Screen"),
                tr("With more than one screen, pick whose taskbar shows the readings."),
                self._screen,
            ),
            self._strip_layout,
        )
        self._add_group(layout, tr("TASKBAR STRIP"), self._strip_rows)
        self._tray_rows = (
            SettingRow(
                tr("Tray icon"),
                tr(
                    "The app keeps a single icon in the notification area. "
                    "Show the logo, or one live reading."
                ),
                self._tray_icon,
            ),
            SettingRow(
                tr("Keep running when closed"),
                tr("Closing the window hides it to the tray instead of quitting."),
                self._close_to_tray,
            ),
            SettingRow(
                tr("Usage alerts"),
                tr(
                    "Notify me when CPU or memory stays high, a drive is "
                    "almost full, the battery is low, or the data limit is near."
                ),
                self._alerts,
            ),
        )
        self._add_group(layout, tr("TRAY & ALERTS"), self._tray_rows)
        self._alert_rows = (
            SettingRow(
                tr("CPU usage above"),
                tr("Alert when the processor stays above this for 30 seconds."),
                self._alert_cpu,
            ),
            SettingRow(
                tr("Memory usage above"),
                tr("Alert when memory stays above this for 30 seconds."),
                self._alert_ram,
            ),
            SettingRow(
                tr("Drive free space below"),
                tr("Alert when any drive has less than this much free."),
                self._alert_drive,
            ),
            SettingRow(
                tr("Battery below"),
                tr("Alert when the battery drops to this level while unplugged."),
                self._alert_battery,
            ),
        )
        self._add_group(layout, tr("ALERT LEVELS"), self._alert_rows)
        self._add_group(
            layout,
            tr("NETWORK"),
            (
                SettingRow(
                    tr("Network adapter"),
                    tr(
                        "Measure speed and data use for one connection, such as Wi-Fi "
                        "or Ethernet. “All adapters” can count VPN traffic twice. Data "
                        "use is counted while System Monitor runs."
                    ),
                    self._adapter,
                ),
                SettingRow(
                    tr("Speed unit"),
                    tr("Show internet speed in bytes (like download managers) or bits (like providers)."),
                    self._speed_unit,
                ),
                SettingRow(
                    tr("Monthly data limit"),
                    tr("Get a warning at 80% and when the limit is reached. Zero means no limit."),
                    self._data_limit,
                ),
            ),
        )
        self._add_group(
            layout,
            tr("REFRESH"),
            (
                SettingRow(
                    tr("Refresh rate"),
                    tr("Slower refresh uses a little less CPU."),
                    self._refresh,
                ),
            ),
        )
        # The window's latest reading adds what's shown for CPU and GPU.
        self._about = AboutPanel(
            lambda: diagnostics.collect(getattr(parent, "last_reading", None)),
            self._run_welcome,
        )
        self._add_group(layout, tr("ABOUT"), (self._about,))

        self._error = QLabel()
        self._error.setObjectName("error")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(24, 12, 24, 18)
        buttons.addStretch(1)
        done = StyledButton(tr("Done"))
        done.setObjectName("primaryButton")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        buttons.addWidget(done)
        outer.addLayout(buttons)

        self._autostart.toggled.connect(self._set_autostart)
        for switch, key in self._bound_switches:
            switch.toggled.connect(
                lambda checked, key=key: self._settings.set_value(key, checked)
            )
        for box, key in self._bound_choices:
            box.currentIndexChanged.connect(
                lambda _=0, box=box, key=key: self._settings.set_value(key, box.currentData())
            )
        for number, key in self._bound_numbers:
            number.valueChanged.connect(
                lambda value, key=key: self._settings.set_value(key, value)
            )
        self._language.currentIndexChanged.connect(self._language_chosen)
        settings.changed.connect(self._sync)
        self._sync()

    @staticmethod
    def _add_group(layout: QVBoxLayout, title: str, rows: tuple[QWidget, ...]) -> None:
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addSpacing(10)
        layout.addWidget(heading)
        group = StyledFrame("settingsGroup", "group")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)
        group.apply_style()
        for index, row in enumerate(rows):
            if index:
                divider = QFrame()
                divider.setObjectName("divider")
                divider.setFixedHeight(1)
                group_layout.addWidget(divider)
            group_layout.addWidget(row)
        layout.addWidget(group)

    def _sync(self, *_) -> None:
        widgets = [switch for switch, _ in self._bound_switches]
        widgets += [box for box, _ in self._bound_choices]
        widgets += [number for number, _ in self._bound_numbers]
        widgets += [self._autostart, self._language]
        for widget in widgets:
            widget.blockSignals(True)

        for switch, key in self._bound_switches:
            switch.setChecked(self._settings.value(key))
        for number, key in self._bound_numbers:
            number.setValue(self._settings.value(key))
        autostart = is_autostart_enabled()
        self._autostart.setChecked(autostart)
        self._autostart.setEnabled(autostart_supported())
        self._minimized_row.setEnabled(autostart and self._tray_available)
        self._sensor_row.setEnabled(self._sensor_app_available)
        if not self._sensor_app_available:
            self._sensor_app.setChecked(False)
        for row in self._strip_rows + self._tray_rows:
            row.setEnabled(self._tray_available)
        strip_on = self._tray_available and self._settings.value(STRIP_VISIBLE)
        for row in self._strip_rows[1:]:
            row.setEnabled(strip_on)
        alerts_on = self._settings.value(ALERTS_ENABLED)
        for row in self._alert_rows:
            row.setEnabled(alerts_on)
        self._strip_layout.sync()
        fill_combo(
            self._font_family, strip_font_choices(), self._settings.value(STRIP_FONT_FAMILY)
        )
        # Choice boxes with fixed items just select the saved value; the rest
        # are rebuilt because their items depend on this PC.
        refilled = (self._font_family, self._screen, self._adapter)
        for box, key in self._bound_choices:
            if box not in refilled:
                box.setCurrentIndex(max(0, box.findData(self._settings.value(key))))
        self._language.setCurrentIndex(
            max(0, self._language.findData(self._settings.value(LANGUAGE)))
        )
        chosen = styles.get(self._settings.value(STYLE))
        self._style_row.description.setText(tr(chosen.description))
        fill_combo(self._screen, screen_choices(), self._settings.value(STRIP_SCREEN))
        saved_adapter = self._settings.value(NETWORK_ADAPTER)
        fill_combo(self._adapter, adapter_choices(saved_adapter), saved_adapter)

        for widget in widgets:
            widget.blockSignals(False)

    def _set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as error:
            self._error.setText(
                tr("Couldn't change the startup setting: {reason}").format(reason=error)
            )
            self._error.show()
        else:
            self._error.hide()
        self._sync()

    def _language_chosen(self) -> None:
        code = self._language.currentData()
        self._settings.set_value(LANGUAGE, code)
        if code == i18n.current_language():
            return
        window = self.parent()
        if hasattr(window, "restart_application") and dialogs.ask(
            self,
            tr("Language"),
            tr("System Monitor needs to restart to change the language. Restart now?"),
            tr("Restart now"),
            tr("Later"),
        ):
            window.restart_application()

    def _run_welcome(self) -> None:
        from welcome import WelcomeDialog

        WelcomeDialog(self._settings, self).exec()

    def apply_theme_colors(self) -> None:
        self._about.apply_theme_colors()
        self._strip_layout.sync()
        for toggle in self.findChildren(ToggleSwitch):
            toggle.apply_style()
        match_title_bar(self)

    def showEvent(self, event) -> None:
        self._sync()
        super().showEvent(event)
        match_title_bar(self)

    def paintEvent(self, event) -> None:
        style = styles.current()
        if style.has_backdrop:
            painter = QPainter(self)
            style.paint_backdrop(painter, QRectF(self.rect()), self.devicePixelRatioF())
            painter.end()
        super().paintEvent(event)
