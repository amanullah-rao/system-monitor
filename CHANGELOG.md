# Changelog

## 1.2.0 — 2026-11-03

- **Welcome page** on the first start: language, theme, what the taskbar strip
  shows, and start with Windows. It can be run again from Settings → About.
- **Korean (한국어)** interface, next to English. The language changes after a
  restart, which the app offers to do.
- **Hover details**: rest the mouse on the taskbar strip to see every CPU core,
  the busiest apps and each connection's speed.
- **Internet data**: a chart of the last 30 days, and an optional monthly
  limit that warns at 80% and when it is reached.
- **All drives** are listed on the dashboard, and the low-space alert covers
  every drive.
- **Speed unit**: show internet speed in bytes (KB/s, MB/s) or bits (Kbps,
  Mbps).
- **Temperature unit**: °C or °F everywhere.
- **Processes**: right-click an app to end it or open its folder, and click CPU
  or Memory to sort the list.
- **Taskbar strip looks**: choose the font, a backdrop behind the text, and a
  color for each reading.
- **Alert levels** are now yours to set: CPU, memory, drive space and battery.
- **Laptops**: the time left on battery, and the charging power where the
  laptop reports it (a new reading for the strip).
- **Updates**: Check for updates can now download the installer, check it
  against GitHub's checksum, and open it.
- **Soft style** (neumorphism): an optional look with rounded shapes that seem
  pressed out of, or into, one surface, in both the dark and the light theme.
  Choose it under Settings → Appearance → Style; Classic stays the default.

## 1.1.2 — 2026-11-03

- Fixed: the taskbar strip stayed on screen during some games and remote
  desktops. Borderless games and Parsec fill the screen while carrying the
  "maximized" flag, which the full-screen check wrongly ruled out. It now also
  asks Windows whether a full-screen app or presentation is active.
- Fixed: the strip's right-click menu opened partly behind the taskbar, which
  hid its lower entries. It now opens fully above the taskbar.

## 1.1.1 — 2026-10-22

- Fixed: a schtasks.exe error could appear when shutting down or signing out
  of Windows. The app no longer starts any program once Windows begins to
  shut down.
- The taskbar strip now steps aside for full-screen apps such as games,
  videos and Parsec, like the Windows taskbar does (Settings → Taskbar strip
  → Hide during full-screen apps).
- GPU temperature: a new reading for the strip and tray icon, also shown in
  the tray tooltip. Temperatures for graphics cards that NVML can't read
  (and as a fallback for NVIDIA) now come from the sensor reader.
- Better CPU temperature support for AMD Ryzen processors.
- When CPU temperature is unavailable, the app says why (for example a
  missing PawnIO driver).
- Settings → About → Copy diagnostic info, for problem reports.

## 1.1.0 — 2026-10-21

First public release.

- Dashboard with CPU, memory, drive, network and GPU readings, history graphs
  and the busiest processes; compact view.
- Taskbar strip with live readings next to the clock: choose the items, order,
  one or two lines, text size and screen. It stays visible when the taskbar or
  the hidden icons are open, and follows an auto-hiding taskbar.
- Data used today and this month, for all network adapters or one connection.
- CPU temperature through the LibreHardwareMonitor library, with no extra
  window or tray icon.
- Single tray icon, usage alerts, start with Windows.
- Dark and light themes, or match Windows.
- Check for updates in Settings → About.
