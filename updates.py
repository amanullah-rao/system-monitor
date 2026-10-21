# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Check GitHub Releases for a newer version, only when the user asks.

The request carries nothing about the PC or the user, only the app's name
and version as its User-Agent, which GitHub requires.
"""

import json
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

import app_info

TIMEOUT_SECONDS = 10
NEWER, CURRENT, NO_RELEASES, FAILED = "newer", "current", "none", "failed"


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3); stops at the first part that isn't a number."""
    numbers = []
    for part in text.strip().lstrip("vV").split("."):
        digits = ""
        for character in part:
            if not character.isdigit():
                break
            digits += character
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def is_newer(latest: str, current: str) -> bool:
    latest_parts, current_parts = parse_version(latest), parse_version(current)
    size = max(len(latest_parts), len(current_parts))
    pad = lambda parts: parts + (0,) * (size - len(parts))  # noqa: E731
    return bool(latest_parts) and pad(latest_parts) > pad(current_parts)


def fetch_latest_release() -> tuple[str, str, str]:
    """(state, version, link or error message); blocks for up to TIMEOUT_SECONDS."""
    request = urllib.request.Request(
        app_info.RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{app_info.APP_NAME.replace(' ', '')}/{app_info.VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return NO_RELEASES, "", app_info.RELEASES_URL
        return FAILED, "", f"GitHub answered with error {error.code}."
    except urllib.error.URLError as error:
        return FAILED, "", f"Couldn't reach GitHub ({error.reason})."
    except (OSError, ValueError) as error:
        return FAILED, "", f"Couldn't read GitHub's answer ({error})."
    version = str(release.get("tag_name", "")).lstrip("vV")
    link = str(release.get("html_url") or app_info.RELEASES_URL)
    if not link.startswith("https://github.com/"):
        link = app_info.RELEASES_URL
    state = NEWER if is_newer(version, app_info.VERSION) else CURRENT
    return state, version, link


class UpdateChecker(QObject):
    """Runs the check on a worker thread and reports back on the GUI thread."""

    finished = Signal(str, str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    def check(self) -> bool:
        """Start a check; False if one is already running."""
        if self._running:
            return False
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self) -> None:
        try:
            result = fetch_latest_release()
        except Exception as error:  # Never let a failed check take down the app.
            result = (FAILED, "", f"Update check failed ({error}).")
        self._running = False
        self.finished.emit(*result)
