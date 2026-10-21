# PyInstaller build for System Monitor. Run build_exe.ps1 rather than this directly.
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# -*- mode: python ; coding: utf-8 -*-

import os
import sys

sys.path.insert(0, SPECPATH)
import app_info  # noqa: E402

# Windows version resource: Explorer's Properties → Details and Task Manager
# show these. Written from app_info so the details live in one place.
numbers = ", ".join((app_info.VERSION.split(".") + ["0"] * 4)[:4])
version_file = os.path.join(workpath, "version_info.txt")
os.makedirs(workpath, exist_ok=True)
strings = {
    "CompanyName": app_info.AUTHOR,
    "FileDescription": app_info.APP_NAME,
    "FileVersion": app_info.VERSION,
    "InternalName": app_info.APP_NAME,
    "LegalCopyright": app_info.COPYRIGHT,
    "OriginalFilename": f"{app_info.APP_NAME}.exe",
    "ProductName": app_info.APP_NAME,
    "ProductVersion": app_info.VERSION,
    "Comments": f"{app_info.DESCRIPTION}. {app_info.GITHUB_URL}",
}
string_structs = ",\n        ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
with open(version_file, "w", encoding="utf-8") as handle:
    handle.write(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
        {string_structs}
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    )

a = Analysis(
    ["main.py"],
    datas=[("assets/app_icon.ico", "assets")],
    # Imported inside a try block; listed so it's bundled when installed.
    hiddenimports=["pynvml"],
    # ssl stays in: "Check for updates" asks GitHub over HTTPS.
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick"],
)

# Qt pieces the app never loads. It uses only QtCore, QtGui, QtWidgets and
# QtNetwork (for the single-instance pipe), drawn without OpenGL.
UNUSED_QT_LIBRARIES = (
    "opengl32sw.dll",
    "qt6quick",
    "qt6qml",
    "qt6pdf",
    "qt6svg",
    "qt6opengl",
    "qt6virtualkeyboard",
)
# Plugins to keep, by folder; any other plugin folder is left out.
KEPT_QT_PLUGINS = {
    "platforms": {"qwindows.dll"},
    "imageformats": {"qico.dll"},  # the app icon is an .ico file
    "styles": None,  # None keeps the whole folder
}


def needed(dest: str) -> bool:
    path = dest.replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    if any(name.startswith(prefix) or name == prefix for prefix in UNUSED_QT_LIBRARIES):
        return False
    if path.startswith("pyside6/translations/"):
        return False
    if path.startswith("pyside6/plugins/"):
        folder = path.split("/")[2]
        if folder not in KEPT_QT_PLUGINS:
            return False
        kept = KEPT_QT_PLUGINS[folder]
        return kept is None or name in kept
    return True


a.binaries = [entry for entry in a.binaries if needed(entry[0])]
a.datas = [entry for entry in a.datas if needed(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="System Monitor",
    icon="assets/app_icon.ico",
    version=version_file,
    console=False,
    # UPX-packed executables are flagged by antivirus far more often.
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="System Monitor", upx=False)
