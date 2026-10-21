# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# Builds System Monitor for Windows:
#   dist\System Monitor\System Monitor.exe   portable folder (needs the whole folder)
#   dist\System Monitor Setup.exe            single-file installer to share
#
#   powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# Change the version (and author details) in app_info.py.
#
# Needs Python 3.12 from python.org, Inno Setup 6 (winget install JRSoftware.InnoSetup)
# and, for CPU temperature, LibreHardwareMonitor (winget install
# LibreHardwareMonitor.LibreHardwareMonitor), whose library the installer bundles.

# Name, version and author come from app_info.py.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$venv = Join-Path $PSScriptRoot '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'

# --- 1. The app, with PyInstaller, in a separate environment so only the
#        app's own dependencies are bundled.
if (-not (Test-Path $python)) {
    py -3.12 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build environment (needs Python 3.12 from python.org).' }
}
& $python -m pip install --disable-pip-version-check --quiet --upgrade pip
& $python -m pip install --disable-pip-version-check --quiet -r requirements.txt 'pyinstaller>=6.10,<7'
if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }

& $python -m PyInstaller --noconfirm --clean SystemMonitor.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

# Put the CPU temperature setup next to the portable exe, where users can find it.
$out = Join-Path $PSScriptRoot 'dist\System Monitor'
Copy-Item sensor_setup.ps1, sensor_install.ps1, sensor_helper.ps1, README.md -Destination $out -Force
"Built: $(Join-Path $out 'System Monitor.exe')"

# --- 2. The LibreHardwareMonitor library and only the assemblies it references.
$lhm = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Directory -Filter 'LibreHardwareMonitor.LibreHardwareMonitor*' |
    Select-Object -First 1
if (-not $lhm -or -not (Test-Path (Join-Path $lhm.FullName 'LibreHardwareMonitorLib.dll'))) {
    throw 'LibreHardwareMonitor is needed to build the installer: winget install LibreHardwareMonitor.LibreHardwareMonitor'
}
$sensorLib = Join-Path $PSScriptRoot 'build\sensor-lib'
if (Test-Path $sensorLib) { Remove-Item $sensorLib -Recurse -Force }
New-Item -ItemType Directory -Path $sensorLib | Out-Null
$seen = New-Object System.Collections.Generic.HashSet[string]
$queue = New-Object System.Collections.Queue
$queue.Enqueue('LibreHardwareMonitorLib')
while ($queue.Count) {
    $name = $queue.Dequeue()
    $file = Join-Path $lhm.FullName "$name.dll"
    if (-not (Test-Path $file) -or -not $seen.Add($name)) { continue }
    Copy-Item $file $sensorLib
    foreach ($reference in [Reflection.Assembly]::ReflectionOnlyLoadFrom($file).GetReferencedAssemblies()) {
        $queue.Enqueue($reference.Name)
    }
}
"Sensor library: $($seen.Count) files"

# --- 3. The installer.
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 is needed to build the installer: winget install JRSoftware.InnoSetup' }
$info = & $python -c "import app_info, json; print(json.dumps({k: v for k, v in vars(app_info).items() if k.isupper()}))" | ConvertFrom-Json
& $iscc /Qp "/DAppVersion=$($info.VERSION)" "/DAppPublisher=$($info.AUTHOR)" `
    "/DAppUrl=$($info.GITHUB_URL)" "/DAppRepoUrl=$($info.REPOSITORY_URL)" "/DAppCopyright=$($info.COPYRIGHT)" "/DAppDescription=$($info.DESCRIPTION)" `
    "/DDistDir=$out" "/DSensorLibDir=$sensorLib" (Join-Path $PSScriptRoot 'installer\SystemMonitor.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed.' }
"Built: $(Join-Path $PSScriptRoot 'dist\System Monitor Setup.exe')"
