# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# Registers the CPU temperature helper. Needs administrator rights.
# Called by the installer and by sensor_setup.ps1; not meant to be run alone.
#
#   -HelperDir  folder holding sensor_helper.ps1 and lib\LibreHardwareMonitorLib.dll;
#               must be writable only by administrators (e.g. under Program Files),
#               because the helper runs with administrator rights.
#   -RemoveLegacyCopy  also delete C:\Program Files\SystemMonitor, where
#               sensor_setup.ps1 installed the helper before the installer existed.

param(
    [Parameter(Mandatory = $true)][string]$HelperDir,
    [switch]$RemoveLegacyCopy
)
$ErrorActionPreference = 'Stop'

$helper = Join-Path $HelperDir 'sensor_helper.ps1'
if (-not (Test-Path -LiteralPath $helper)) { throw "Missing $helper" }

# Any user can create folders in ProgramData, so recreate ours from scratch:
# a folder made earlier by someone else would keep that owner and its contents.
$data = Join-Path $env:ProgramData 'SystemMonitor'
if (Test-Path -LiteralPath $data) { Remove-Item -LiteralPath $data -Recurse -Force }
New-Item -ItemType Directory -Path $data | Out-Null
# Owner: Administrators. SYSTEM and Administrators: full control. Users: read only.
& icacls $data /setowner '*S-1-5-32-544' | Out-Null
& icacls $data /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls failed with exit code $LASTEXITCODE" }

# On demand only: System Monitor runs and ends this task itself. "Highest"
# lets the signed-in user start it elevated without a UAC prompt each time.
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
# conhost --headless runs PowerShell without flashing a console window.
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\conhost.exe" `
    -Argument "--headless powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$helper`"" `
    -WorkingDirectory $HelperDir
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'SystemMonitorSensors' `
    -Description 'Started and stopped by System Monitor to read CPU temperature.' `
    -Action $action -Principal $principal -Settings $settings -Force | Out-Null

# Earlier approaches, no longer needed.
Unregister-ScheduledTask -TaskName 'LibreHardwareMonitor' -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName 'Block remote access to LibreHardwareMonitor (8085)' -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule
if ($RemoveLegacyCopy) {
    $legacy = Join-Path $env:ProgramFiles 'SystemMonitor'
    $resolvedHelperDir = (Resolve-Path -LiteralPath $HelperDir).Path
    if ((Test-Path -LiteralPath $legacy) -and -not $resolvedHelperDir.StartsWith($legacy + '\')) {
        Remove-Item -LiteralPath $legacy -Recurse -Force
    }
}
