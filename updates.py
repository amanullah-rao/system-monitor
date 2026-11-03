# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Check GitHub Releases for a newer version, and download it, only on request.

The requests carry nothing about the PC or the user, only the app's name and
version as the User-Agent, which GitHub requires. A downloaded installer is
checked against the SHA-256 that GitHub lists for the file before it is used.
"""

import hashlib
import json
import re
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

import app_info
from i18n import tr

TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 30
NEWER, CURRENT, NO_RELEASES, FAILED = "newer", "current", "none", "failed"
# Only installers published by this project's releases are downloaded.
DOWNLOAD_PREFIX = f"{app_info.REPOSITORY_URL}/releases/download/"
ASSET_NAME = re.compile(r"^SystemMonitor-Setup-\d+(\.\d+)*\.exe$")
TEMP_PREFIX = "SystemMonitor-update-"


@dataclass(frozen=True)
class ReleaseInfo:
    state: str
    version: str = ""
    link: str = ""  # the release page
    message: str = ""  # what went wrong, when it did
    asset_url: str = ""
    asset_name: str = ""
    asset_size: int = 0
    sha256: str = ""

    @property
    def can_download(self) -> bool:
        """Whether the installer can be fetched and verified here."""
        return bool(
            self.asset_url.startswith(DOWNLOAD_PREFIX)
            and ASSET_NAME.match(self.asset_name)
            and re.fullmatch(r"[0-9a-f]{64}", self.sha256)
        )


class UpdateError(Exception):
    pass


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


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{app_info.APP_NAME.replace(' ', '')}/{app_info.VERSION}",
        },
    )


def _find_installer(release: dict) -> dict:
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and ASSET_NAME.match(str(asset.get("name", ""))):
            return asset
    return {}


def fetch_latest_release() -> ReleaseInfo:
    """Ask GitHub for the latest release; blocks for up to TIMEOUT_SECONDS."""
    try:
        with urllib.request.urlopen(
            _request(app_info.RELEASES_API), timeout=TIMEOUT_SECONDS
        ) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return ReleaseInfo(NO_RELEASES, link=app_info.RELEASES_URL)
        return ReleaseInfo(
            FAILED, message=tr("GitHub answered with error {code}.").format(code=error.code)
        )
    except urllib.error.URLError as error:
        return ReleaseInfo(
            FAILED, message=tr("Couldn't reach GitHub ({reason}).").format(reason=error.reason)
        )
    except (OSError, ValueError) as error:
        return ReleaseInfo(
            FAILED,
            message=tr("Couldn't read GitHub's answer ({reason}).").format(reason=error),
        )
    version = str(release.get("tag_name", "")).lstrip("vV")
    link = str(release.get("html_url") or app_info.RELEASES_URL)
    if not link.startswith("https://github.com/"):
        link = app_info.RELEASES_URL
    asset = _find_installer(release)
    digest = str(asset.get("digest", ""))
    return ReleaseInfo(
        NEWER if is_newer(version, app_info.VERSION) else CURRENT,
        version=version,
        link=link,
        asset_url=str(asset.get("browser_download_url", "")),
        asset_name=str(asset.get("name", "")),
        asset_size=int(asset.get("size") or 0),
        sha256=digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else "",
    )


def _remove_old_downloads() -> None:
    for folder in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*"):
        shutil.rmtree(folder, ignore_errors=True)


def download_installer(
    info: ReleaseInfo, progress: Callable[[int, int], None] | None = None
) -> Path:
    """Download the installer and verify it; raises UpdateError if that fails."""
    if not info.can_download:
        raise UpdateError(tr("This release can't be verified for automatic download."))
    _remove_old_downloads()
    folder = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
    target = folder / info.asset_name
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(
            _request(info.asset_url), timeout=DOWNLOAD_TIMEOUT_SECONDS
        ) as response, open(target, "wb") as out:
            total = int(response.headers.get("Content-Length") or info.asset_size or 0)
            done = 0
            while chunk := response.read(64 * 1024):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if info.asset_size and target.stat().st_size != info.asset_size:
            raise UpdateError(tr("The download was incomplete."))
        if digest.hexdigest() != info.sha256:
            raise UpdateError(tr("The download didn't match GitHub's checksum, so it was discarded."))
    except UpdateError:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except (OSError, ValueError) as error:
        shutil.rmtree(folder, ignore_errors=True)
        raise UpdateError(tr("The download failed ({reason}).").format(reason=error)) from error
    return target


class UpdateChecker(QObject):
    """Runs the check on a worker thread and reports back on the GUI thread."""

    finished = Signal(object)  # a ReleaseInfo

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
            info = fetch_latest_release()
        except Exception as error:  # Never let a failed check take down the app.
            info = ReleaseInfo(FAILED, message=tr("Update check failed ({reason}).").format(reason=error))
        self._running = False
        self.finished.emit(info)


class UpdateDownloader(QObject):
    """Downloads the installer on a worker thread, reporting progress."""

    progress = Signal(int, int)  # bytes done, bytes total (0 when unknown)
    downloaded = Signal(str)  # path of the verified installer
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._running = False

    def start(self, info: ReleaseInfo) -> bool:
        if self._running:
            return False
        self._running = True
        threading.Thread(target=self._run, args=(info,), daemon=True).start()
        return True

    def _run(self, info: ReleaseInfo) -> None:
        try:
            path = download_installer(info, self.progress.emit)
        except UpdateError as error:
            self._running = False
            self.failed.emit(str(error))
        except Exception as error:  # Never let a failed download take down the app.
            self._running = False
            self.failed.emit(tr("The download failed ({reason}).").format(reason=error))
        else:
            self._running = False
            self.downloaded.emit(str(path))
