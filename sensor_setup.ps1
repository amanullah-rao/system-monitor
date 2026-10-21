# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# CPU temperature setup when running System Monitor from source (py main.py).
# The installer does this itself. Run as administrator:
#   powershell -ExecutionPolicy Bypass -File sensor_setup.ps1
#
# Copies sensor_helper.ps1 and LibreHardwareMonitorLib (from the winget
# LibreHardwareMonitor package) to C:\Program Files\SystemMonitor, where only
# administrators can change them, then registers the helper with
# sensor_install.ps1.

param([string]$Log)
$ErrorActionPreference = 'Stop'

function Write-Result([string]$text) {
    if ($Log) { $text | Out-File -FilePath $Log -Encoding utf8 } else { $text }
}

try {
    $lhm = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Directory -Filter 'LibreHardwareMonitor.LibreHardwareMonitor*' |
        Select-Object -First 1
    if (-not $lhm -or -not (Test-Path (Join-Path $lhm.FullName 'LibreHardwareMonitorLib.dll'))) {
        throw 'LibreHardwareMonitor is not installed. Run: winget install LibreHardwareMonitor.LibreHardwareMonitor'
    }

    $app = Join-Path $env:ProgramFiles 'SystemMonitor'
    New-Item -ItemType Directory -Force -Path (Join-Path $app 'lib') | Out-Null
    Copy-Item (Join-Path $lhm.FullName '*.dll') (Join-Path $app 'lib') -Force
    Copy-Item (Join-Path $PSScriptRoot 'sensor_helper.ps1') $app -Force

    & (Join-Path $PSScriptRoot 'sensor_install.ps1') -HelperDir $app
    Write-Result 'OK'
} catch {
    Write-Result "ERROR: $($_.Exception.Message)"
}
