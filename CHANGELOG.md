# Changelog

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
