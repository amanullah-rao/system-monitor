# System Monitor for Windows

A lightweight Windows 10/11 app that shows CPU, memory, drive, network, GPU and
CPU temperature readings live — in a dashboard window, in the notification
area, and as text right on the taskbar (like TrafficMonitor). Built with Python
and PySide6.

## Features

- **Dashboard** with gauges, history sparklines, GPU details and the busiest
  processes; a **compact view** shows just the key numbers.
- **Taskbar strip** — readings as text directly on the taskbar, next to the
  clock: upload and download speed, CPU, RAM, CPU and GPU temperature, GPU
  usage, drive space, disk activity, battery, time since start-up, and data
  used today or this month. Pick what to show, set the order, choose one or
  two lines, a text size, and which screen's taskbar to use. It stays visible
  when you click the taskbar or open the hidden icons (^), slides away and
  back with an auto-hiding taskbar, and steps aside for full-screen games,
  videos and remote desktops such as Parsec (this can be turned off).
- **Data usage** — internet data used today and this month, for all adapters
  or one connection (Wi-Fi, Ethernet, …). It's counted while the app runs.
- **One tray icon** showing the app logo or one live reading, with a summary
  on hover and every option on right-click.
- **CPU and GPU temperature** through the LibreHardwareMonitor library (Intel
  and AMD Ryzen processors; NVIDIA, AMD and Intel graphics), with no extra
  window or tray icon (see below).
- **Usage alerts** when CPU or memory stays above 90%, the system drive is
  almost full, or the battery is low.
- **Dark or light theme**, or match the app mode set in Windows; it switches
  straight away.
- Starts with Windows if you like, refreshes every ½ second by default, and
  uses about 3% of one CPU core and around 150 MB of memory.

## Download and install

Download the latest **SystemMonitor-Setup-x.y.z.exe** from the
[Releases page](https://github.com/amanullah-rao/system-monitor/releases) and
run it. It installs to Program Files with a Start menu shortcut, can start the
app when you sign in, and sets up CPU temperature (one administrator prompt).
Installing a newer version over an older one updates it and keeps your
settings. Uninstall it from **Settings → Apps** like any other app.

The installer isn't code-signed yet, so Windows SmartScreen may say "Windows
protected your PC". Click **More info → Run anyway** if you downloaded it from
the Releases page above.

**Check for updates** is in **Settings → About**. It only runs when you click
it.

## CPU temperature

Windows doesn't give apps the CPU temperature on most PCs; reading it needs
administrator rights and a hardware driver. With the **Show CPU temperature**
option (on by default), the installer:

- installs the signed [PawnIO](https://pawnio.eu) driver with winget if it's
  missing,
- puts a small sensor reader (`sensor_helper.ps1` and the LibreHardwareMonitor
  library) in the app folder in Program Files, which only administrators can
  change,
- registers an on-demand Task Scheduler task, `SystemMonitorSensors`, that
  runs the reader with highest privileges.

System Monitor starts that task when it opens and ends it when you quit, with
no prompt each time; the reader also stops by itself if the app closes
unexpectedly. It writes readings to `C:\ProgramData\SystemMonitor\sensors.json`
once a second (only administrators can write there) and opens no network port.

Without it, the app can start the LibreHardwareMonitor app instead (which shows
its own tray icon) or fall back to Windows' ACPI sensors, which most PCs don't
fill in. Everything else works without a temperature sensor.

## Privacy

System Monitor doesn't collect or send anything. The only network request it
ever makes is **Check for updates**, which asks GitHub for the latest release
when you click it. Settings stay in your Windows user profile, and data usage
is kept in `%LOCALAPPDATA%\System Monitor\data_usage.json`.

## Tips

- Drag the taskbar strip sideways to move it; double-click it to open the
  window; right-click it for options.
- Windows 11 may put the tray icon in the hidden icons (^) menu. To keep it in
  view, drag it onto the taskbar, or turn on **System Monitor** under
  **Settings → Personalization → Taskbar → Other system tray icons**.
- Closing the window keeps the app running in the tray; use **Quit** in the
  tray menu to exit.
- Only one copy runs at a time; opening it again brings the window forward.
- GPU usage and memory are shown for NVIDIA cards (through NVML). Other
  adapters are listed without live usage, with their temperature when the
  sensor reader can read it.
- If a reading is missing, hover it for the reason (for example a missing
  PawnIO driver), or use **Settings → About → Copy diagnostic info** and paste
  the result into a [problem report](https://github.com/amanullah-rao/system-monitor/issues).
  It holds hardware and sensor details only.

## Run from source

Needs Python 3.10 or newer.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

For CPU temperature when running from source, install LibreHardwareMonitor
(`winget install LibreHardwareMonitor.LibreHardwareMonitor`, which also
installs PawnIO), then run once as administrator:

```powershell
powershell -ExecutionPolicy Bypass -File sensor_setup.ps1
```

## Build the installer

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Set the version in `app_info.py` first. The build needs Python 3.12 from
python.org (it uses a separate `.venv-build` environment, so only the app's
dependencies are bundled), Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
and LibreHardwareMonitor for its library. It creates:

- `dist\System Monitor Setup.exe` — the single-file installer to share;
- `dist\System Monitor\` — the same app as a portable folder (copy the whole
  folder, not just the .exe).

Neither needs Python on the target PC (Windows 10/11, 64-bit).

## Project files

- `main.py` — entry point
- `app_info.py` — name, version, author and repository details used everywhere
- `system_monitor.py` — metric sampling, process list, GPU and CPU temperature
- `sampler.py` — background thread that samples on a fixed schedule
- `data_usage.py` — data used per day
- `metrics.py` — the readings the taskbar strip and tray icon can show
- `taskbar_strip.py` — text overlay on the taskbar
- `tray.py` — tray icon, tooltip and menu
- `alerts.py` — usage notifications
- `updates.py` — **Check for updates**
- `diagnostics.py` — **Copy diagnostic info**
- `widgets.py` — dashboard window, cards, gauges and sparklines
- `settings.py`, `settings_dialog.py` — saved preferences and the Settings window
- `theme.py`, `formatting.py` — colors, styles, icon and number formatting
- `sensor_app.py` — starts and stops the CPU temperature reader with the app
- `sensor_helper.ps1` — the CPU temperature reader (runs elevated)
- `sensor_install.ps1`, `sensor_uninstall.ps1`, `sensor_setup.ps1` — register
  and remove the reader
- `build_exe.ps1`, `SystemMonitor.spec`, `installer/` — the .exe and installer
- `assets/` — the logo and app icon

## License

Copyright © 2026 Amanullah.

System Monitor is free software, licensed under the
[GNU General Public License v3.0](LICENSE) (GPL-3.0-only). You may use, study,
share and change it. If you share it or anything made from it, you must keep
the copyright notices, say what you changed, and release your version's
complete source code under the same license. It comes with no warranty.

The installer also bundles third-party components under their own licenses;
see [installer/THIRD_PARTY_NOTICES.txt](installer/THIRD_PARTY_NOTICES.txt).

### Name and logo

The GPL covers the code only. The name "System Monitor by Amanullah" and the
neon logo in `assets/` are not licensed for use in other projects. If you
publish a modified version, give it a different name and logo so that it
isn't mistaken for this app.

### Contributing

Pull requests are welcome. By sending one, you agree that your contribution
is licensed under the same GPL-3.0-only license.

## Author

Made by **Amanullah** ([github.com/amanullah-rao](https://github.com/amanullah-rao)).
Found a problem or have an idea?
[Open an issue](https://github.com/amanullah-rao/system-monitor/issues).
