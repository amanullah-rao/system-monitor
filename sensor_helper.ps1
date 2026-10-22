# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah
# Publishes CPU and graphics card temperatures for System Monitor without any
# window or tray icon.
#
# Installed to Program Files by sensor_setup.ps1 and started elevated through
# the "SystemMonitorSensors" scheduled task, because reading CPU temperature
# needs administrator rights. Stops by itself when System Monitor exits.

$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $MyInvocation.MyCommand.Path
$output = Join-Path $env:ProgramData 'SystemMonitor\sensors.json'
# System Monitor listens on this pipe (its single-instance check) while it runs.
$ownerPipe = '\\.\pipe\LocalSystemTools.SystemMonitor'
$started = Get-Date

Add-Type -Namespace SystemMonitor -Name NativePipe -MemberDefinition @'
[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
public static extern bool WaitNamedPipe(string name, uint timeout);
'@

function Get-OwnerAlive {
    # WaitNamedPipe checks that the pipe exists without connecting to it.
    # A file wouldn't work: Store Python redirects AppData writes elsewhere.
    $exists = [SystemMonitor.NativePipe]::WaitNamedPipe($ownerPipe, 1)
    $fileNotFound = 2
    if ($exists -or [Runtime.InteropServices.Marshal]::GetLastWin32Error() -ne $fileNotFound) {
        return $true
    }
    # Give System Monitor a moment to open its pipe after starting us.
    return ((Get-Date) - $started).TotalSeconds -lt 15
}

Add-Type -Path (Join-Path $base 'lib\LibreHardwareMonitorLib.dll')
$computer = New-Object LibreHardwareMonitor.Hardware.Computer
$computer.IsCpuEnabled = $true
# Graphics cards too: their temperatures for cards NVML can't read (AMD, Intel).
$computer.IsGpuEnabled = $true
$computer.Open()
try {
    while (Get-OwnerAlive) {
        $temperatures = @()
        foreach ($hardware in $computer.Hardware) {
            $hardware.Update()
            foreach ($sensor in $hardware.Sensors) {
                if ($sensor.SensorType -eq 'Temperature' -and $null -ne $sensor.Value) {
                    $temperatures += [pscustomobject]@{
                        name     = $sensor.Name
                        value    = [double]$sensor.Value
                        hardware = [string]$hardware.HardwareType  # Cpu, GpuNvidia, GpuAmd, GpuIntel
                        device   = $hardware.Name
                    }
                }
            }
        }
        $json = [pscustomobject]@{
            updated      = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000
            temperatures = $temperatures
        } | ConvertTo-Json -Compress -Depth 4
        # Write then rename so readers never see a half-written file.
        [IO.File]::WriteAllText("$output.tmp", $json)
        Move-Item -LiteralPath "$output.tmp" -Destination $output -Force
        Start-Sleep -Milliseconds 1000
    }
} finally {
    $computer.Close()
    Remove-Item -LiteralPath $output -ErrorAction SilentlyContinue
}
