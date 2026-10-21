# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# Removes what sensor_install.ps1 and System Monitor set up. Run by the uninstaller
# with administrator rights.
#
#   -AppDir  install folder; the sign-in entry is removed only if it points there.

param([string]$AppDir)

& schtasks /end /tn SystemMonitorSensors 2>$null | Out-Null
Unregister-ScheduledTask -TaskName 'SystemMonitorSensors' -Confirm:$false -ErrorAction SilentlyContinue

$data = Join-Path $env:ProgramData 'SystemMonitor'
if (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Recurse -Force -ErrorAction SilentlyContinue }

# System Monitor's "Start with Windows" setting writes this value itself.
$run = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$entry = (Get-ItemProperty -Path $run -Name SystemMonitor -ErrorAction SilentlyContinue).SystemMonitor
if ($entry -and $AppDir -and $entry.ToLower().Contains($AppDir.TrimEnd('\').ToLower())) {
    Remove-ItemProperty -Path $run -Name SystemMonitor -ErrorAction SilentlyContinue
}
