# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Interface language: English, or Korean from translations_ko.py.

Wrap every on-screen sentence in tr(). The language is chosen at start-up (or
in the welcome page before any window exists), so tr() can be called freely
while the interface is built. Text without a translation stays in English.
Texts with values use named placeholders, so a translation can reorder them:

    tr("{used} of {total} used").format(used=..., total=...)
"""

LANGUAGES = (("en", "English"), ("ko", "한국어"))

_language = "en"
_table: dict[str, str] = {}


def set_language(code: str) -> None:
    global _language, _table
    if code == "ko":
        from translations_ko import KOREAN

        _language, _table = "ko", KOREAN
    else:
        _language, _table = "en", {}


def current_language() -> str:
    return _language


def N_(text: str) -> str:
    """Mark a sentence for translation without translating it yet.

    For text defined at import time, before the language is chosen; pass it
    through tr() where it's shown.
    """
    return text


def tr(text: str) -> str:
    return _table.get(text, text)


def system_language() -> str:
    """"ko" when Windows is set to Korean, otherwise "en"."""
    from PySide6.QtCore import QLocale

    return "ko" if QLocale.system().language() == QLocale.Language.Korean else "en"
