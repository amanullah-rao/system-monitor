# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

"""Name, version and author details, shared by the app, the .exe and the installer.

Bump VERSION here before building a release; build_exe.ps1 reads it.
"""

APP_NAME = "System Monitor"
VERSION = "1.1.0"
DESCRIPTION = "Live CPU, memory, disk, network and temperature monitor for Windows"
AUTHOR = "Amanullah"
GITHUB_URL = "https://github.com/amanullah-rao"
COPYRIGHT = f"© 2026 {AUTHOR}"
LICENSE = "GNU GPL v3"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"

# The project's GitHub repository; releases there are what "Check for
# updates" looks for.
REPOSITORY = "amanullah-rao/system-monitor"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
RELEASES_URL = f"{REPOSITORY_URL}/releases"
# Where people report problems; there's no public email address.
ISSUES_URL = f"{REPOSITORY_URL}/issues"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
