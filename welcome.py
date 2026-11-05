# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""The welcome page: a few questions that set the app up the way the user likes."""

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import i18n
import styles
import theme
from i18n import tr
from styles import StyledButton, StyledFrame
from metrics import STRIP_PRESETS
from settings import (
    FIRST_RUN_DONE,
    LANGUAGE,
    STYLE,
    STRIP_FONT_FAMILY,
    STRIP_FONT_SIZE,
    STRIP_ITEMS,
    STRIP_ROWS,
    STRIP_VISIBLE,
    THEME,
    AppSettings,
    autostart_supported,
    is_autostart_enabled,
    set_autostart,
)
from settings_dialog import SettingRow, StripPreview, ToggleSwitch
from theme import THEME_CHOICES, make_app_icon, match_title_bar


def pill_row(
    options: list[tuple[object, str]], current: object, on_pick: Callable[[object], None],
    columns: int = 0,
) -> QWidget:
    """A row of one-of-many buttons; with `columns` they wrap into a grid."""
    holder = QWidget()
    layout = QGridLayout(holder) if columns else QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    group = QButtonGroup(holder)
    group.setExclusive(True)
    for index, (value, label) in enumerate(options):
        button = StyledButton(label)
        button.setObjectName("pill")
        button.setCheckable(True)
        button.setChecked(value == current)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False, value=value: on_pick(value))
        group.addButton(button)
        if columns:
            layout.addWidget(button, index // columns, index % columns)
        else:
            layout.addWidget(button)
    if columns:
        layout.setColumnStretch(columns, 1)
    else:
        layout.addStretch(1)
    holder.group = group  # kept alive with the row
    return holder


def card(*rows: QWidget) -> QFrame:
    frame = StyledFrame("settingsGroup", "group")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    frame.apply_style()
    for index, row in enumerate(rows):
        if index:
            divider = QFrame()
            divider.setObjectName("divider")
            divider.setFixedHeight(1)
            layout.addWidget(divider)
        layout.addWidget(row)
    return frame


class WelcomeDialog(QDialog):
    """First-run (or "run again") setup. Choices apply as they're made."""

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        first_run: bool = False,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        # The language can only be switched here before the app's windows exist.
        self._first_run = first_run
        self._content: QWidget | None = None
        self.resize(560, 680)
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._build()

    def _build(self) -> None:
        """(Re)create the page, so a language change shows straight away."""
        if self._content is not None:
            self._outer.removeWidget(self._content)
            self._content.deleteLater()
        self.setWindowTitle(tr("Welcome to System Monitor"))
        settings = self._settings
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(make_app_icon().pixmap(56, 56))
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel(tr("Welcome to System Monitor"))
        title.setObjectName("appTitle")
        subtitle = QLabel(
            tr(
                "Choose how it should look and what it shows. You can change all of "
                "this later in Settings."
            )
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addWidget(logo)
        header.addLayout(titles, 1)
        layout.addLayout(header)
        layout.addSpacing(6)

        if self._first_run:
            layout.addWidget(self._section(tr("Language")))
            layout.addWidget(
                card(
                    self._pick_row(
                        pill_row(
                            list(i18n.LANGUAGES),
                            i18n.current_language(),
                            self._language_picked,
                        )
                    )
                )
            )

        layout.addWidget(self._section(tr("Style")))
        layout.addWidget(
            card(
                self._pick_row(
                    pill_row(
                        [(value, tr(label)) for value, label in styles.choices()],
                        settings.value(STYLE),
                        lambda value: settings.set_value(STYLE, value),
                        columns=4,
                    )
                )
            )
        )

        layout.addWidget(self._section(tr("Theme")))
        layout.addWidget(
            card(
                self._pick_row(
                    pill_row(
                        [(mode, tr(label)) for mode, label in THEME_CHOICES],
                        settings.value(THEME),
                        lambda mode: settings.set_value(THEME, mode),
                    )
                )
            )
        )

        layout.addWidget(self._section(tr("Readings on the taskbar")))
        self._strip_toggle = ToggleSwitch()
        self._strip_toggle.setChecked(settings.value(STRIP_VISIBLE))
        self._strip_toggle.toggled.connect(
            lambda checked: settings.set_value(STRIP_VISIBLE, checked)
        )
        self._preview = StripPreview()
        self._refresh_preview()
        presets = [
            (",".join(keys), tr(name)) for name, keys in STRIP_PRESETS
        ]
        current = settings.value(STRIP_ITEMS)
        layout.addWidget(
            card(
                SettingRow(
                    tr("Show readings next to the clock"),
                    tr("Speed, CPU, memory and more, right on the taskbar."),
                    self._strip_toggle,
                ),
                self._pick_row(
                    pill_row(presets, current, self._preset_picked), self._preview
                ),
            )
        )

        layout.addWidget(self._section(tr("Startup")))
        self._autostart = ToggleSwitch()
        self._autostart.setChecked(is_autostart_enabled())
        self._autostart.setEnabled(autostart_supported())
        self._autostart.toggled.connect(self._autostart_toggled)
        self._error = QLabel()
        self._error.setObjectName("error")
        self._error.setWordWrap(True)
        self._error.hide()
        layout.addWidget(
            card(
                SettingRow(
                    tr("Start with Windows"),
                    tr("Open System Monitor automatically when you sign in."),
                    self._autostart,
                )
            )
        )
        layout.addWidget(self._error)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        start = StyledButton(tr("Get started"))
        start.setObjectName("primaryButton")
        start.setDefault(True)
        start.clicked.connect(self.accept)
        buttons.addWidget(start)
        layout.addLayout(buttons)

        self._content = content
        self._outer.addWidget(content)
        match_title_bar(self)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("sectionTitle")
        return label

    @staticmethod
    def _pick_row(pills: QWidget, extra: QWidget | None = None) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(pills)
        if extra is not None:
            layout.addWidget(extra)
        return holder

    def _refresh_preview(self) -> None:
        self._preview.set_layout(
            self._settings.keys(STRIP_ITEMS),
            self._settings.value(STRIP_ROWS),
            self._settings.value(STRIP_FONT_SIZE),
            self._settings.value(STRIP_FONT_FAMILY),
            self._settings.colors(),
        )

    def _preset_picked(self, joined: str) -> None:
        self._settings.set_keys(STRIP_ITEMS, joined.split(","))
        self._refresh_preview()

    def _language_picked(self, code: str) -> None:
        i18n.set_language(code)
        self._settings.set_value(LANGUAGE, code)
        self._build()

    def _autostart_toggled(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except OSError as error:
            self._error.setText(
                tr("Couldn't change the startup setting: {reason}").format(reason=error)
            )
            self._error.show()
            self._autostart.blockSignals(True)
            self._autostart.setChecked(is_autostart_enabled())
            self._autostart.blockSignals(False)
        else:
            self._error.hide()

    def done(self, result: int) -> None:
        # Closing the page by any route counts as seen, so it isn't shown again.
        self._settings.set_value(FIRST_RUN_DONE, True)
        super().done(result)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        match_title_bar(self)

    def paintEvent(self, event) -> None:
        style = styles.current()
        if style.has_backdrop:
            painter = QPainter(self)
            style.paint_backdrop(painter, QRectF(self.rect()), self.devicePixelRatioF())
            painter.end()
        super().paintEvent(event)
