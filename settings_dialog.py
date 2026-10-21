# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import sys
from html import escape

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from metrics import (
    METRICS,
    PREVIEW_VALUES,
    STRIP_PRESETS,
    TRAY_ICON_CHOICES,
    MetricValue,
    in_order,
)
from settings import (
    ALERTS_ENABLED,
    CLOSE_TO_TRAY,
    MANAGE_SENSOR_APP,
    REFRESH_SECONDS,
    START_MINIMIZED,
    NETWORK_ADAPTER,
    STRIP_COLORED,
    STRIP_FONT_SIZE,
    STRIP_ITEMS,
    STRIP_ROWS,
    STRIP_SCREEN,
    STRIP_VISIBLE,
    THEME,
    TRAY_ICON,
    AppSettings,
    autostart_supported,
    is_autostart_enabled,
    set_autostart,
)
import app_info
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
import theme
from theme import THEME_CHOICES, make_app_icon, match_title_bar
from updates import CURRENT, NEWER, NO_RELEASES, UpdateChecker

REFRESH_CHOICES = (
    (0.5, "Every ½ second"),
    (1.0, "Every second"),
    (2.0, "Every 2 seconds"),
    (5.0, "Every 5 seconds"),
)
ROW_CHOICES = ((2, "Two lines (stacked)"), (1, "One line"))
FONT_CHOICES = ((8.0, "Small"), (9.0, "Normal"), (10.0, "Large"), (11.0, "Extra large"))


def screen_choices() -> list[tuple[str, str]]:
    """(device name, label) for the screen picker; "" follows the main screen."""
    primary = QGuiApplication.primaryScreen()
    monitors = list_monitors()
    taskbars = find_taskbars(monitors)
    choices = [("", "Main screen")]
    for number, screen in enumerate(QGuiApplication.screens(), start=1):
        device = screen_device_name(screen, monitors)
        size = screen.geometry().size() * screen.devicePixelRatio()
        label = f"Screen {number}: {screen.model() or device} ({size.width()}×{size.height()})"
        if screen == primary:
            label += " · main"
        if taskbars and device not in taskbars:
            label += " · no taskbar"
        choices.append((device, label))
    return choices


def adapter_choices(saved: str) -> list[tuple[str, str]]:
    """(adapter name, label) for the network picker; "" measures all of them."""
    choices = [("", "All adapters")]
    adapters = network_adapters()
    for name, connected in adapters:
        choices.append((name, name if connected else f"{name} (not connected)"))
    if saved and saved not in {name for name, _ in adapters}:
        choices.append((saved, f"{saved} (not found)"))
    return choices


def fill_combo(combo: QComboBox, choices, current) -> None:
    """Replace a combo box's items without emitting change signals."""
    combo.blockSignals(True)
    combo.clear()
    for value, label in choices:
        combo.addItem(label, value)
    combo.setCurrentIndex(max(0, combo.findData(current)))
    combo.blockSignals(False)


class NoWheelComboBox(QComboBox):
    """A combo box that leaves the mouse wheel to the page.

    Otherwise scrolling the Settings page changes whichever choice happens
    to pass under the pointer. Click it (or use the keyboard) to change it.
    """

    def wheelEvent(self, event) -> None:
        event.ignore()


class ToggleSwitch(QAbstractButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QColor(theme.ACCENT if self.isChecked() else theme.SWITCH_OFF)
        knob = QColor("#ffffff")
        if not self.isEnabled():
            track.setAlpha(80)
            knob = QColor(theme.DISABLED)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(22 if self.isChecked() else 2, 2, 20, 20))


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
        self.setFixedHeight(48)

    def set_layout(self, keys: list[str], rows: int, font_size: float) -> None:
        self._font = strip_font(font_size)
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
        values = {key: MetricValue(text) for key, text in PREVIEW_VALUES.items()}
        paint_columns(
            painter, self.height(), self._columns, values, False, False, self._font
        )


class StripLayoutEditor(QWidget):
    """Choose, order and group what the taskbar strip shows."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(6)

        heading = QLabel("Layout and order")
        heading.setObjectName("primary")
        note = QLabel(
            "Tick what to show and use the arrows (or drag) to set the order. "
            "With two lines, each pair in the list shares a column."
        )
        note.setObjectName("small")
        note.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(note)
        layout.addSpacing(4)

        self.preview = StripPreview()
        layout.addWidget(self.preview)
        layout.addSpacing(6)

        presets_label = QLabel("Quick presets")
        presets_label.setObjectName("small")
        layout.addWidget(presets_label)
        presets = QGridLayout()
        presets.setHorizontalSpacing(8)
        presets.setVerticalSpacing(8)
        for index, (name, keys) in enumerate(STRIP_PRESETS):
            button = QPushButton(name)
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
        up = QPushButton("▲  Move up")
        down = QPushButton("▼  Move down")
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        buttons.addWidget(up)
        buttons.addWidget(down)
        buttons.addStretch(1)
        editor.addWidget(self.list, 1)
        editor.addLayout(buttons)
        layout.addLayout(editor)
        layout.addSpacing(6)

        rows_line = QHBoxLayout()
        rows_label = QLabel("Lines")
        rows_label.setObjectName("primary")
        self.rows = NoWheelComboBox()
        for rows, label in ROW_CHOICES:
            self.rows.addItem(label, rows)
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

    def sync(self) -> None:
        saved = [metric.key for metric in in_order(self._settings.keys(STRIP_ITEMS))]
        rows = self._settings.value(STRIP_ROWS)
        # Rebuild only when the list disagrees, so an unticked item stays put.
        if self.list.count() != len(METRICS) or self._checked_keys() != saved:
            self.list.blockSignals(True)
            self.list.clear()
            unchecked = [metric for metric in METRICS if metric.key not in saved]
            for metric in in_order(saved) + unchecked:
                item = QListWidgetItem(f"{metric.name}   ·   shows as “{metric.short}”")
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
        self.rows.blockSignals(True)
        self.rows.setCurrentIndex(max(0, self.rows.findData(rows)))
        self.rows.blockSignals(False)
        self.preview.set_layout(saved, rows, self._settings.value(STRIP_FONT_SIZE))

    def _save(self, *_) -> None:
        keys = self._checked_keys()
        if not keys:
            # At least one reading must stay on the strip.
            self.list.clear()
            self.sync()
            return
        self._settings.set_keys(STRIP_ITEMS, keys)
        self.preview.set_layout(
            keys, self._settings.value(STRIP_ROWS), self._settings.value(STRIP_FONT_SIZE)
        )

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

    def _apply_preset(self, keys: tuple[str, ...]) -> None:
        self._settings.set_keys(STRIP_ITEMS, list(keys))
        self.list.clear()
        self.sync()


class AboutPanel(QWidget):
    def __init__(self) -> None:
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
        description = QLabel(app_info.DESCRIPTION)
        description.setObjectName("small")
        description.setWordWrap(True)
        author = QLabel(f"Made by {app_info.AUTHOR}")
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
        self._check_button = QPushButton("Check for updates")
        self._check_button.setToolTip(
            "Asks GitHub for the latest release. Nothing about this PC is sent."
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
        layout.addLayout(text, 1)

        self._checker = UpdateChecker(self)
        self._checker.finished.connect(self._show_update_result)
        self._update_result: tuple[str, str, str] | None = None
        self.apply_theme_colors()

    def apply_theme_colors(self) -> None:
        link_style = f"color: {theme.ACCENT}; text-decoration: none;"
        separator = "&nbsp;&nbsp;·&nbsp;&nbsp;"
        self._links.setText(
            f'<a style="{link_style}" href="{app_info.REPOSITORY_URL}">Project page</a>'
            f"{separator}"
            f'<a style="{link_style}" href="{app_info.ISSUES_URL}">Report a problem</a>'
            f"{separator}"
            f'<a style="{link_style}" href="{app_info.GITHUB_URL}">GitHub profile</a>'
        )
        self._legal.setText(
            f"{escape(app_info.COPYRIGHT)}. Free software under the "
            f'<a style="{link_style}" href="{app_info.LICENSE_URL}">{app_info.LICENSE}</a>'
            ", with ABSOLUTELY NO WARRANTY."
        )
        if self._update_result is not None:
            self._show_update_result(*self._update_result)

    def _check_for_updates(self) -> None:
        if self._checker.check():
            self._check_button.setEnabled(False)
            self._update_status.setText("Checking…")

    def _show_update_result(self, state: str, version: str, detail: str) -> None:
        self._update_result = (state, version, detail)
        self._check_button.setEnabled(True)
        link_style = f"color: {theme.ACCENT}; text-decoration: none;"
        if state == NEWER:
            self._update_status.setText(
                f'<span style="color:{theme.GREEN}">Version {escape(version)} is available.</span>'
                f'&nbsp;&nbsp;<a style="{link_style}" href="{escape(detail)}">Download</a>'
            )
        elif state == CURRENT:
            self._update_status.setText(f"You have the latest version ({app_info.VERSION}).")
        elif state == NO_RELEASES:
            self._update_status.setText("No releases have been published yet.")
        else:
            self._update_status.setText(escape(detail))


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
        self.setWindowTitle("Settings")
        self.resize(600, 780)

        self._autostart = ToggleSwitch()
        self._minimized = ToggleSwitch()
        self._sensor_app = ToggleSwitch()
        self._strip = ToggleSwitch()
        self._colored = ToggleSwitch()
        self._close_to_tray = ToggleSwitch()
        self._alerts = ToggleSwitch()
        self._refresh = NoWheelComboBox()
        for seconds, label in REFRESH_CHOICES:
            self._refresh.addItem(label, seconds)
        self._bound_switches = (
            (self._minimized, START_MINIMIZED),
            (self._sensor_app, MANAGE_SENSOR_APP),
            (self._strip, STRIP_VISIBLE),
            (self._colored, STRIP_COLORED),
            (self._close_to_tray, CLOSE_TO_TRAY),
            (self._alerts, ALERTS_ENABLED),
        )
        self._strip_layout = StripLayoutEditor(settings)
        self._tray_icon = NoWheelComboBox()
        for key, label in TRAY_ICON_CHOICES:
            self._tray_icon.addItem(label, key)
        self._font_size = NoWheelComboBox()
        for points, label in FONT_CHOICES:
            self._font_size.addItem(label, points)
        self._screen = NoWheelComboBox()
        self._adapter = NoWheelComboBox()
        self._theme = NoWheelComboBox()
        for mode, label in THEME_CHOICES:
            self._theme.addItem(label, mode)
        self._adapter.setMinimumWidth(180)

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

        title = QLabel("Settings")
        title.setObjectName("appTitle")
        subtitle = QLabel("Changes are saved automatically.")
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._minimized_row = SettingRow(
            "Start hidden",
            "When Windows starts the app, keep it in the tray instead of opening the window.",
            self._minimized,
        )
        self._add_group(
            layout,
            "STARTUP",
            (
                SettingRow(
                    "Start with Windows",
                    "Open System Monitor automatically when you sign in.",
                    self._autostart,
                ),
                self._minimized_row,
            ),
        )
        self._add_group(
            layout,
            "APPEARANCE",
            (
                SettingRow(
                    "Theme",
                    "Dark, light, or follow the app mode set in Windows.",
                    self._theme,
                ),
            ),
        )
        if not sensor_app_available:
            sensor_text = (
                "CPU temperature isn't set up on this PC. Run the System Monitor "
                "installer again and keep “Show CPU temperature” ticked."
                if getattr(sys, "frozen", False)
                else "CPU temperature isn't set up on this PC. Install "
                "LibreHardwareMonitor, then run sensor_setup.ps1 as administrator."
            )
        elif sensor_app_shows_tray_icon:
            sensor_text = (
                "Starts LibreHardwareMonitor with this app and closes it when you quit. "
                "It shows its own tray icon; run sensor_setup.ps1 as administrator "
                "once to read the sensors without it."
            )
        else:
            sensor_text = (
                "Reads CPU temperature in the background, with no extra window or "
                "tray icon. Starts with this app and stops when you quit."
            )
        self._sensor_row = SettingRow(
            "CPU temperature sensor", sensor_text, self._sensor_app
        )
        self._add_group(layout, "SENSORS", (self._sensor_row,))
        self._strip_rows = (
            SettingRow(
                "Show on the taskbar",
                "Live readings next to the clock. Drag them to move.",
                self._strip,
            ),
            SettingRow(
                "Color warnings",
                "Turn a reading amber or red when it gets high.",
                self._colored,
            ),
            SettingRow(
                "Text size",
                "Larger text is easier to read; two lines fit up to Extra large.",
                self._font_size,
            ),
            SettingRow(
                "Screen",
                "With more than one screen, pick whose taskbar shows the readings.",
                self._screen,
            ),
            self._strip_layout,
        )
        self._add_group(layout, "TASKBAR STRIP", self._strip_rows)
        self._tray_rows = (
            SettingRow(
                "Tray icon",
                "The app keeps a single icon in the notification area. "
                "Show the logo, or one live reading.",
                self._tray_icon,
            ),
            SettingRow(
                "Keep running when closed",
                "Closing the window hides it to the tray instead of quitting.",
                self._close_to_tray,
            ),
            SettingRow(
                "Usage alerts",
                "Notify me when CPU or memory stays above 90%, the drive is "
                "almost full, or the battery is low.",
                self._alerts,
            ),
        )
        self._add_group(layout, "TRAY & ALERTS", self._tray_rows)
        self._add_group(
            layout,
            "NETWORK",
            (
                SettingRow(
                    "Network adapter",
                    "Measure speed and data use for one connection, such as Wi-Fi "
                    "or Ethernet. “All adapters” can count VPN traffic twice. Data "
                    "use is counted while System Monitor runs.",
                    self._adapter,
                ),
            ),
        )
        self._add_group(
            layout,
            "REFRESH",
            (
                SettingRow(
                    "Refresh rate",
                    "Slower refresh uses a little less CPU.",
                    self._refresh,
                ),
            ),
        )
        self._about = AboutPanel()
        self._add_group(layout, "ABOUT", (self._about,))

        self._error = QLabel()
        self._error.setObjectName("error")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(self._error)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(24, 12, 24, 18)
        buttons.addStretch(1)
        done = QPushButton("Done")
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
        self._refresh.currentIndexChanged.connect(
            lambda: self._settings.set_value(REFRESH_SECONDS, self._refresh.currentData())
        )
        self._tray_icon.currentIndexChanged.connect(
            lambda: self._settings.set_value(TRAY_ICON, self._tray_icon.currentData())
        )
        self._font_size.currentIndexChanged.connect(
            lambda: self._settings.set_value(STRIP_FONT_SIZE, self._font_size.currentData())
        )
        self._screen.currentIndexChanged.connect(
            lambda: self._settings.set_value(STRIP_SCREEN, self._screen.currentData())
        )
        self._theme.currentIndexChanged.connect(
            lambda: self._settings.set_value(THEME, self._theme.currentData())
        )
        self._adapter.currentIndexChanged.connect(
            lambda: self._settings.set_value(NETWORK_ADAPTER, self._adapter.currentData())
        )
        settings.changed.connect(self._sync)
        self._sync()

    @staticmethod
    def _add_group(layout: QVBoxLayout, title: str, rows: tuple[QWidget, ...]) -> None:
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addSpacing(10)
        layout.addWidget(heading)
        group = QFrame()
        group.setObjectName("settingsGroup")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(0)
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
        widgets += [
            self._autostart,
            self._refresh,
            self._tray_icon,
            self._font_size,
            self._theme,
        ]
        for widget in widgets:
            widget.blockSignals(True)

        for switch, key in self._bound_switches:
            switch.setChecked(self._settings.value(key))
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
        self._strip_layout.sync()
        self._tray_icon.setCurrentIndex(
            max(0, self._tray_icon.findData(self._settings.value(TRAY_ICON)))
        )
        index = self._refresh.findData(self._settings.value(REFRESH_SECONDS))
        self._refresh.setCurrentIndex(max(index, 0))
        self._font_size.setCurrentIndex(
            max(0, self._font_size.findData(self._settings.value(STRIP_FONT_SIZE)))
        )
        self._theme.setCurrentIndex(max(0, self._theme.findData(self._settings.value(THEME))))
        fill_combo(self._screen, screen_choices(), self._settings.value(STRIP_SCREEN))
        saved_adapter = self._settings.value(NETWORK_ADAPTER)
        fill_combo(self._adapter, adapter_choices(saved_adapter), saved_adapter)

        for widget in widgets:
            widget.blockSignals(False)

    def _set_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as error:
            self._error.setText(f"Couldn't change the startup setting: {error}")
            self._error.show()
        else:
            self._error.hide()
        self._sync()

    def apply_theme_colors(self) -> None:
        self._about.apply_theme_colors()
        self._strip_layout.update()
        match_title_bar(self)

    def showEvent(self, event) -> None:
        self._sync()
        super().showEvent(event)
        match_title_bar(self)
