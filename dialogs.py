# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Small message boxes whose buttons follow the app's language."""

from PySide6.QtWidgets import QMessageBox, QWidget

from i18n import tr


def _box(parent: QWidget | None, icon, title: str, text: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    return box


def ask(parent: QWidget | None, title: str, text: str, yes: str, no: str | None = None) -> bool:
    """A question with two named buttons; True when the first is chosen."""
    box = _box(parent, QMessageBox.Icon.Question, title, text)
    yes_button = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    no_button = box.addButton(no or tr("Cancel"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no_button)
    box.exec()
    return box.clickedButton() is yes_button


def inform(parent: QWidget | None, title: str, text: str) -> None:
    box = _box(parent, QMessageBox.Icon.Information, title, text)
    box.addButton(tr("OK"), QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def warn(parent: QWidget | None, title: str, text: str) -> None:
    box = _box(parent, QMessageBox.Icon.Warning, title, text)
    box.addButton(tr("OK"), QMessageBox.ButtonRole.AcceptRole)
    box.exec()
