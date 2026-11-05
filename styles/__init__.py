# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""The interface styles. Pick one with activate(); read it with current()."""

from .classic import Classic
from .fluent import Fluent
from .glass import Glass
from .hud import Hud
from .modern import Modern
from .registry import activate, choices, current, get, register
from .skeuo import Skeuo
from .soft import Soft
from .widgets import StyledButton, StyledFrame, refresh_all

# Registration order is the order they are offered in.
for _style in (Classic(), Soft(), Fluent(), Modern(), Glass(), Skeuo(), Hud()):
    register(_style)

__all__ = [
    "StyledButton", "StyledFrame", "activate", "choices", "current", "get", "refresh_all",
]
