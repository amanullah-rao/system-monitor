# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Which styles exist and which one is active."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Style

CLASSIC = "classic"

_styles: dict[str, "Style"] = {}
_current: "Style | None" = None


def register(style: "Style") -> None:
    _styles[style.name] = style


def get(name: str) -> "Style":
    """A style by name; Classic for anything unknown."""
    return _styles.get(name) or _styles[CLASSIC]


def current() -> "Style":
    return _current or _styles[CLASSIC]


def activate(name: str) -> "Style":
    global _current
    _current = get(name)
    return _current


def choices() -> list[tuple[str, str]]:
    """(name, English label) for every style, in display order."""
    return [(style.name, style.label) for style in _styles.values()]
