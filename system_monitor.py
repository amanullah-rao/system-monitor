# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 Amanullah

import ctypes
import json
import os
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass, replace

import psutil

from data_usage import DataUsageTracker
from sensor_app import (
    SESSION_ENDING,
    helper_gpu_temperatures,
    read_helper_output,
    sensor_problem,
)


@dataclass(frozen=True)
class GpuReading:
    name: str
    utilization: float | None
    memory_used_mb: float | None
    memory_total_mb: float | None
    temperature_c: float | None
    error: str | None = None


@dataclass(frozen=True)
class ProcessReading:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float


@dataclass(frozen=True)
class SystemReading:
    cpu_percent: float
    logical_cpus: int
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    memory_total_gb: float
    disk_percent: float | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    disk_free_gb: float | None
    disk_name: str
    network_sent_mbps: float
    network_received_mbps: float
    network_sent_total_bytes: int
    network_received_total_bytes: int
    # The adapter measured; empty for all adapters together.
    network_adapter: str
    data_today_received: int
    data_today_sent: int
    data_month_received: int
    data_month_sent: int
    disk_read_bytes_per_s: float | None
    disk_write_bytes_per_s: float | None
    battery_percent: float | None
    battery_plugged: bool | None
    uptime_seconds: float
    gpus: tuple[GpuReading, ...]
    gpu_status: str
    cpu_temperature_c: float | None
    cpu_temperature_status: str
    processes: tuple[ProcessReading, ...]
    timestamp: float


# Keeps PowerShell from flashing a console window when the app runs under
# pythonw.exe (as it does when started with Windows).
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

NO_SENSOR_MESSAGE = (
    "Windows doesn't share the CPU temperature with apps on this PC. "
    "Run LibreHardwareMonitor as administrator to show it here."
)
LHM_WEB_URL = "http://127.0.0.1:8085/data.json"
# Preferred LibreHardwareMonitor sensor names, best first.
# Intel CPUs report "CPU Package"; AMD Ryzen CPUs report "Core (Tctl/Tdie)".
LHM_PREFERRED_SENSORS = (
    "CPU Package",
    "Core Max",
    "Core (Tctl/Tdie)",
    "CPU (Tctl/Tdie)",
    "CCDs Max (Tdie)",
    "Core (Tctl)",
    "Package",
    "Core Average",
)


def network_adapters() -> list[tuple[str, bool]]:
    """Network adapter names with whether each is connected, connected first."""
    try:
        stats = psutil.net_if_stats()
        names = set(stats) | set(psutil.net_io_counters(pernic=True))
    except (OSError, RuntimeError):
        return []
    adapters = [
        (name, bool(name in stats and stats[name].isup))
        for name in names
        if not name.lower().startswith("loopback")
    ]
    adapters.sort(key=lambda adapter: (not adapter[1], adapter[0].lower()))
    return adapters


class CpuTemperatureCollector:
    """Read CPU temperature from optional Windows hardware-monitor sensors."""

    POLL_INTERVAL_SECONDS = 5
    # Querying sensors starts PowerShell, so check less often when none exist,
    # except at first while LibreHardwareMonitor may still be starting.
    NO_SENSOR_POLL_INTERVAL_SECONDS = 30
    STARTUP_GRACE_SECONDS = 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reading: tuple[float | None, str] = (
            None,
            "Looking for a CPU temperature sensor",
        )
        self._last_poll = -float("inf")
        self._in_progress = False
        self._started = time.monotonic()

    def read(self) -> tuple[float | None, str]:
        with self._lock:
            starting = time.monotonic() - self._started < self.STARTUP_GRACE_SECONDS
            interval = (
                self.POLL_INTERVAL_SECONDS
                if self._reading[0] is not None or starting
                else self.NO_SENSOR_POLL_INTERVAL_SECONDS
            )
            if (
                not self._in_progress
                and not SESSION_ENDING.is_set()
                and time.monotonic() - self._last_poll >= interval
            ):
                self._in_progress = True
                threading.Thread(target=self._poll, daemon=True).start()
            return self._reading

    def _poll(self) -> None:
        result: tuple[float | None, str] | None = None
        try:
            result = self._query_sensors()
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            result = (None, f"CPU temperature sensor query failed: {error}")
        finally:
            # Always clear the in-progress flag so an unexpected error cannot
            # stop future polls.
            with self._lock:
                if result is not None:
                    self._reading = result
                self._last_poll = time.monotonic()
                self._in_progress = False

    @classmethod
    def _query_sensors(cls) -> tuple[float | None, str]:
        helper_reading = cls._query_sensor_helper()
        if helper_reading is not None:
            return helper_reading
        web_reading = cls._query_lhm_web_server()
        if web_reading is not None:
            return web_reading
        temperature, status = cls._query_wmi_sensors()
        if temperature is None:
            # Say what's missing when it's known, such as the PawnIO driver.
            status = sensor_problem() or status
        return temperature, status

    @staticmethod
    def _query_sensor_helper() -> tuple[float, str] | None:
        """Read the windowless helper started by sensor_app (see sensor_helper.ps1)."""
        data = read_helper_output()
        if data is None:
            return None
        found: dict[str, float] = {}
        for sensor in data.get("temperatures") or []:
            if not isinstance(sensor, dict):
                continue
            # Older helpers listed CPU sensors only and had no hardware field.
            if sensor.get("hardware", "Cpu") != "Cpu":
                continue
            name = str(sensor.get("name", ""))
            try:
                value = float(sensor.get("value"))
            except (TypeError, ValueError):
                continue
            if "Distance" not in name and 0 < value <= 120:
                found[name] = value
        return CpuTemperatureCollector._pick(found, "System Monitor sensor helper")

    @staticmethod
    def _pick(found: dict[str, float], source: str) -> tuple[float, str] | None:
        if not found:
            return None
        for name in LHM_PREFERRED_SENSORS:
            if name in found:
                return found[name], f"{name} ({source})"
        name = max(found, key=found.get)
        return found[name], f"{name} ({source})"

    @staticmethod
    def _query_lhm_web_server() -> tuple[float, str] | None:
        """Read LibreHardwareMonitor's optional local web server (Options → Remote Web Server)."""
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(LHM_WEB_URL, timeout=1) as response:
                tree = json.load(response)
        except (OSError, ValueError):
            return None

        found: dict[str, float] = {}

        def walk(node: dict, in_cpu: bool) -> None:
            in_cpu = in_cpu or "cpu" in str(node.get("ImageURL", "")).lower()
            children = node.get("Children") or []
            value = str(node.get("Value", ""))
            if in_cpu and not children and "°C" in value:
                try:
                    temperature = float(value.replace("°C", "").replace(",", ".").strip())
                except ValueError:
                    temperature = None
                if temperature is not None and 0 < temperature <= 120:
                    found.setdefault(str(node.get("Text", "")), temperature)
            for child in children:
                if isinstance(child, dict):
                    walk(child, in_cpu)

        if isinstance(tree, dict):
            walk(tree, False)
        return CpuTemperatureCollector._pick(found, "LibreHardwareMonitor")

    @staticmethod
    def _query_wmi_sensors() -> tuple[float | None, str]:
        # LibreHardwareMonitor sensor identifiers look like /intelcpu/0/temperature/0;
        # matching on them avoids picking up "GPU Core" temperatures.
        command = r"""
$rows = @()
try {
    $rows = @(Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor -ErrorAction Stop |
        Where-Object { $_.SensorType -eq 'Temperature' -and $_.Identifier -match 'cpu' } |
        ForEach-Object { [pscustomobject]@{ temperature_c = [double]$_.Value; sensor = [string]$_.Name; source = 'LibreHardwareMonitor' } })
} catch {}
if ($rows.Count -eq 0) {
    try {
        $rows = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop |
            Where-Object { $_.InstanceName -match 'CPU|Package|Core' } |
            ForEach-Object { [pscustomobject]@{ temperature_c = ([double]$_.CurrentTemperature / 10) - 273.15; sensor = [string]$_.InstanceName; source = 'Windows ACPI' } })
    } catch {}
}
$rows = @($rows | Where-Object { $_.temperature_c -ge 0 -and $_.temperature_c -le 120 } |
    Sort-Object -Property temperature_c -Descending)
ConvertTo-Json -InputObject $rows -Compress
"""
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
            creationflags=NO_WINDOW,
        )
        payload = json.loads(completed.stdout)
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list) or not payload:
            return None, NO_SENSOR_MESSAGE

        sensor = payload[0]
        temperature = float(sensor["temperature_c"])
        if not 0 <= temperature <= 120:
            return None, "CPU temperature sensor returned an invalid reading"
        return temperature, f"{sensor['sensor']} ({sensor['source']})"


class GpuCollector:
    """Enumerate Windows display adapters and read NVIDIA telemetry through NVML."""

    def __init__(self) -> None:
        self._adapter_names, adapter_error = self._detect_windows_adapters()
        self._nvml = None
        self._nvml_initialized = False
        self._handles = []
        self._nvml_names = []
        self._nvml_error = "nvidia-ml-py is not installed"
        try:
            import pynvml
        except ImportError:
            pynvml = None

        if pynvml is not None:
            self._nvml = pynvml
            try:
                pynvml.nvmlInit()
                self._nvml_initialized = True
                count = pynvml.nvmlDeviceGetCount()
                for index in range(count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                    name = pynvml.nvmlDeviceGetName(handle)
                    if isinstance(name, bytes):
                        name = name.decode("utf-8", errors="replace")
                    self._handles.append(handle)
                    self._nvml_names.append(name)
                self._nvml_error = (
                    "" if count else "NVML did not report any NVIDIA GPUs"
                )
            except pynvml.NVMLError as error:
                self._nvml_error = f"NVML could not read GPU devices: {error}"

        self.status = self._make_status(adapter_error)

    @staticmethod
    def _detect_windows_adapters() -> tuple[tuple[str, ...], str | None]:
        command = (
            "$adapters = Get-CimInstance -ClassName Win32_VideoController "
            "| Select-Object -ExpandProperty Name; "
            "ConvertTo-Json -InputObject @($adapters) -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
                creationflags=NO_WINDOW,
            )
        except FileNotFoundError:
            return (), "PowerShell was not found; Windows GPU enumeration failed"
        except subprocess.TimeoutExpired:
            return (), "Windows GPU enumeration timed out"
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or str(error)
            return (), f"Windows GPU enumeration failed: {detail}"

        try:
            names = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            return (), f"Windows GPU enumeration returned invalid data: {error}"
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list):
            return (), "Windows GPU enumeration returned an unexpected result"
        return tuple(str(name).strip() for name in names if str(name).strip()), None

    def _make_status(self, adapter_error: str | None) -> str:
        if adapter_error:
            adapter_status = adapter_error
        elif self._adapter_names:
            count = len(self._adapter_names)
            adapter_status = (
                f"{count} display adapter{'s' if count != 1 else ''} detected"
            )
        else:
            adapter_status = "No display adapters reported by Windows"

        if self._handles:
            return (
                f"{adapter_status}; NVIDIA utilization and memory telemetry available"
            )
        detail = self._nvml_error or "NVML is unavailable"
        return (
            f"{adapter_status}; GPU utilization and memory telemetry unavailable: "
            f"{detail}"
        )

    def read(self) -> tuple[GpuReading, ...]:
        telemetry: list[GpuReading] = []
        if self._nvml is not None:
            for index, handle in enumerate(self._handles):
                name = self._nvml_names[index]
                try:
                    utilization = self._nvml.nvmlDeviceGetUtilizationRates(handle)
                    memory = self._nvml.nvmlDeviceGetMemoryInfo(handle)
                    telemetry.append(
                        GpuReading(
                            name=name,
                            utilization=float(utilization.gpu),
                            memory_used_mb=memory.used / (1024 * 1024),
                            memory_total_mb=memory.total / (1024 * 1024),
                            temperature_c=self._read_temperature(handle),
                        )
                    )
                except self._nvml.NVMLError as error:
                    telemetry.append(
                        GpuReading(
                            name=name or f"NVIDIA GPU {index}",
                            utilization=None,
                            memory_used_mb=None,
                            memory_total_mb=None,
                            temperature_c=None,
                            error=str(error),
                        )
                    )

        readings = []
        unmatched_telemetry = list(telemetry)
        for adapter_name in self._adapter_names:
            normalized = adapter_name.casefold()
            match = next(
                (
                    reading
                    for reading in unmatched_telemetry
                    if normalized in reading.name.casefold()
                    or reading.name.casefold() in normalized
                ),
                None,
            )
            if match is not None:
                unmatched_telemetry.remove(match)
                readings.append(match)
            else:
                readings.append(
                    GpuReading(
                        name=adapter_name,
                        utilization=None,
                        memory_used_mb=None,
                        memory_total_mb=None,
                        temperature_c=None,
                        error="no NVML telemetry for this adapter",
                    )
                )
        readings.extend(unmatched_telemetry)
        return tuple(readings)

    def _read_temperature(self, handle) -> float | None:
        if self._nvml is None:
            return None
        try:
            sensor = self._nvml.NVML_TEMPERATURE_GPU
            return float(self._nvml.nvmlDeviceGetTemperature(handle, sensor))
        except self._nvml.NVMLError:
            return None

    def close(self) -> None:
        if self._nvml is not None and self._nvml_initialized:
            try:
                self._nvml.nvmlShutdown()
            except self._nvml.NVMLError:
                pass
        self._nvml_initialized = False
        self._handles = []
        self._nvml_names = []


class _UnicodeString(ctypes.Structure):
    _fields_ = [
        ("Length", ctypes.c_ushort),
        ("MaximumLength", ctypes.c_ushort),
        ("Buffer", ctypes.c_void_p),
    ]


class _SystemProcessInformation(ctypes.Structure):
    # Leading fields of SYSTEM_PROCESS_INFORMATION; ctypes applies the same
    # natural alignment as the Windows headers on 32- and 64-bit Python.
    _fields_ = [
        ("NextEntryOffset", ctypes.c_ulong),
        ("NumberOfThreads", ctypes.c_ulong),
        ("WorkingSetPrivateSize", ctypes.c_longlong),
        ("HardFaultCount", ctypes.c_ulong),
        ("NumberOfThreadsHighWatermark", ctypes.c_ulong),
        ("CycleTime", ctypes.c_ulonglong),
        ("CreateTime", ctypes.c_longlong),
        ("UserTime", ctypes.c_longlong),
        ("KernelTime", ctypes.c_longlong),
        ("ImageName", _UnicodeString),
        ("BasePriority", ctypes.c_long),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", ctypes.c_ulong),
        ("SessionId", ctypes.c_ulong),
        ("UniqueProcessKey", ctypes.c_size_t),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
    ]


class WindowsProcessSnapshot:
    """Read every process in one NtQuerySystemInformation call.

    psutil opens each process separately and, for protected processes, takes
    a full system snapshot per process, which costs ~450 ms for ~250
    processes. One snapshot for all of them takes a few milliseconds.
    """

    SYSTEM_PROCESS_INFORMATION_CLASS = 5
    STATUS_INFO_LENGTH_MISMATCH = 0xC0000004 - 2**32

    def __init__(self) -> None:
        self._query = ctypes.windll.ntdll.NtQuerySystemInformation
        self._query.restype = ctypes.c_long
        self._buffer = ctypes.create_string_buffer(512 * 1024)
        # pid -> (create time, total CPU time in 100 ns units, monotonic time)
        self._previous: dict[int, tuple[int, int, float]] = {}

    def _snapshot(self) -> None:
        returned = ctypes.c_ulong()
        while True:
            status = self._query(
                self.SYSTEM_PROCESS_INFORMATION_CLASS,
                self._buffer,
                len(self._buffer),
                ctypes.byref(returned),
            )
            if status != self.STATUS_INFO_LENGTH_MISMATCH:
                break
            # Grow with headroom; processes can start between calls.
            self._buffer = ctypes.create_string_buffer(
                max(returned.value, len(self._buffer)) * 2
            )
        if status < 0:
            raise OSError(f"NtQuerySystemInformation failed: 0x{status & 0xFFFFFFFF:08X}")

    def top_processes(
        self, logical_cpus: int, total_memory: int, limit: int = 10
    ) -> tuple[ProcessReading, ...]:
        self._snapshot()
        now = time.monotonic()
        current: dict[int, tuple[int, int, float]] = {}
        readings = []
        offset = 0
        while True:
            entry = _SystemProcessInformation.from_buffer(self._buffer, offset)
            pid = entry.UniqueProcessId or 0
            if pid:
                cpu_time = entry.UserTime + entry.KernelTime
                current[pid] = (entry.CreateTime, cpu_time, now)
                previous = self._previous.get(pid)
                cpu_percent = 0.0
                # A new create time means Windows reused the PID for another process.
                if previous is not None and previous[0] == entry.CreateTime:
                    elapsed = now - previous[2]
                    if elapsed > 0:
                        cpu_seconds = (cpu_time - previous[1]) / 10_000_000
                        cpu_percent = max(
                            0.0, cpu_seconds / elapsed / logical_cpus * 100
                        )
                name = (
                    ctypes.wstring_at(entry.ImageName.Buffer, entry.ImageName.Length // 2)
                    if entry.ImageName.Buffer
                    else "Unknown process"
                )
                rss = entry.WorkingSetSize
                readings.append(
                    ProcessReading(
                        pid=pid,
                        name=name,
                        cpu_percent=min(cpu_percent, 100.0),
                        memory_mb=rss / (1024**2),
                        memory_percent=rss / total_memory * 100,
                    )
                )
            if not entry.NextEntryOffset:
                break
            offset += entry.NextEntryOffset
        self._previous = current
        readings.sort(key=lambda process: process.cpu_percent, reverse=True)
        return tuple(readings[:limit])


class SystemMonitor:
    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)
        self._gpu_collector = GpuCollector()
        self._cpu_temperature_collector = CpuTemperatureCollector()
        self._processes: dict[int, psutil.Process] = {}
        # Adapter to measure, set by the sampler; empty for all adapters.
        self.network_adapter = ""
        self._previous_adapter = ""
        self._previous_network = self._read_network()
        self._data_usage = DataUsageTracker()
        self._gpu_temperatures: dict[str, float] = {}
        self._gpu_temperatures_read = -float("inf")
        self._previous_disk_io = self._read_disk_io()
        self._boot_time = psutil.boot_time()
        self._previous_time = time.monotonic()
        self._system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        self._logical_cpus = psutil.cpu_count(logical=True) or 1
        self._process_snapshot = (
            WindowsProcessSnapshot() if os.name == "nt" else None
        )

    def close(self) -> None:
        self._gpu_collector.close()
        self._data_usage.save()

    def sample(self) -> SystemReading:
        now = time.monotonic()
        elapsed = max(now - self._previous_time, 0.001)
        network = self._read_network()
        previous = self._previous_network
        if network is None or previous is None or self.network_adapter != self._previous_adapter:
            # Just switched adapter, or it's missing: no fair comparison yet.
            sent_bytes = received_bytes = 0
        else:
            sent_bytes = max(0, network.bytes_sent - previous.bytes_sent)
            received_bytes = max(0, network.bytes_recv - previous.bytes_recv)
        self._previous_network = network
        self._previous_adapter = self.network_adapter
        self._previous_time = now
        self._data_usage.add(received_bytes, sent_bytes)
        today_received, today_sent = self._data_usage.today()
        month_received, month_sent = self._data_usage.month()

        disk_io = self._read_disk_io()
        if disk_io is not None and self._previous_disk_io is not None:
            disk_read = max(0, disk_io.read_bytes - self._previous_disk_io.read_bytes) / elapsed
            disk_write = max(0, disk_io.write_bytes - self._previous_disk_io.write_bytes) / elapsed
        else:
            disk_read = disk_write = None
        self._previous_disk_io = disk_io

        try:
            battery = psutil.sensors_battery()
        except (OSError, RuntimeError):
            battery = None

        memory = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(self._system_drive)
            disk_percent = float(disk.percent)
            disk_used_gb = disk.used / (1024**3)
            disk_total_gb = disk.total / (1024**3)
            disk_free_gb = disk.free / (1024**3)
        except OSError:
            disk_percent = None
            disk_used_gb = None
            disk_total_gb = None
            disk_free_gb = None

        processes = self._read_processes()
        cpu_temperature_c, cpu_temperature_status = (
            self._cpu_temperature_collector.read()
        )
        return SystemReading(
            cpu_percent=psutil.cpu_percent(interval=None),
            logical_cpus=self._logical_cpus,
            memory_percent=float(memory.percent),
            memory_used_gb=memory.used / (1024**3),
            memory_available_gb=memory.available / (1024**3),
            memory_total_gb=memory.total / (1024**3),
            disk_percent=disk_percent,
            disk_used_gb=disk_used_gb,
            disk_total_gb=disk_total_gb,
            disk_free_gb=disk_free_gb,
            disk_name=self._system_drive,
            network_sent_mbps=sent_bytes * 8 / elapsed / 1_000_000,
            network_received_mbps=received_bytes * 8 / elapsed / 1_000_000,
            network_sent_total_bytes=network.bytes_sent if network else 0,
            network_received_total_bytes=network.bytes_recv if network else 0,
            network_adapter=self.network_adapter,
            data_today_received=today_received,
            data_today_sent=today_sent,
            data_month_received=month_received,
            data_month_sent=month_sent,
            disk_read_bytes_per_s=disk_read,
            disk_write_bytes_per_s=disk_write,
            battery_percent=float(battery.percent) if battery is not None else None,
            battery_plugged=battery.power_plugged if battery is not None else None,
            uptime_seconds=max(0.0, time.time() - self._boot_time),
            gpus=self._read_gpus(),
            gpu_status=self._gpu_collector.status,
            cpu_temperature_c=cpu_temperature_c,
            cpu_temperature_status=cpu_temperature_status,
            processes=processes,
            timestamp=time.time(),
        )

    def _read_gpus(self) -> tuple[GpuReading, ...]:
        """NVML readings, with temperatures from the sensor helper where NVML has none.

        The helper (LibreHardwareMonitor) also covers AMD and Intel graphics.
        """
        gpus = self._gpu_collector.read()
        if all(gpu.temperature_c is not None for gpu in gpus):
            return gpus
        # The helper writes once a second; reading every other second is plenty.
        if time.monotonic() - self._gpu_temperatures_read >= 2:
            self._gpu_temperatures = helper_gpu_temperatures()
            self._gpu_temperatures_read = time.monotonic()
        temperatures = self._gpu_temperatures
        if not temperatures:
            return gpus
        filled = []
        for gpu in gpus:
            if gpu.temperature_c is None:
                name = gpu.name.casefold()
                match = next(
                    (
                        value
                        for device, value in temperatures.items()
                        if device.casefold() in name or name in device.casefold()
                    ),
                    None,
                )
                if match is not None:
                    gpu = replace(gpu, temperature_c=match)
            filled.append(gpu)
        return tuple(filled)

    def _read_network(self):
        # None when the chosen adapter is missing (unplugged or disabled).
        try:
            if not self.network_adapter:
                return psutil.net_io_counters()
            return psutil.net_io_counters(pernic=True).get(self.network_adapter)
        except (OSError, RuntimeError):
            return None

    @staticmethod
    def _read_disk_io():
        # Returns None when Windows disk performance counters are disabled.
        try:
            return psutil.disk_io_counters()
        except (OSError, RuntimeError):
            return None

    def _read_processes(self) -> tuple[ProcessReading, ...]:
        if self._process_snapshot is not None:
            try:
                return self._process_snapshot.top_processes(
                    self._logical_cpus, psutil.virtual_memory().total
                )
            except OSError:
                # Fall back to psutil for the rest of the session.
                self._process_snapshot = None
        return self._read_processes_with_psutil()

    def _read_processes_with_psutil(self) -> tuple[ProcessReading, ...]:
        readings = []
        active_pids = set()
        total_memory = psutil.virtual_memory().total

        for discovered in psutil.process_iter():
            pid = discovered.pid
            if pid == 0:
                continue
            active_pids.add(pid)
            process = self._processes.get(pid, discovered)
            try:
                if process is not discovered and not process.is_running():
                    process = discovered
                self._processes[pid] = process
                with process.oneshot():
                    name = process.name() or "Unknown process"
                    cpu_percent = (
                        process.cpu_percent(interval=None) / self._logical_cpus
                    )
                    memory = process.memory_info()
                readings.append(
                    ProcessReading(
                        pid=pid,
                        name=name,
                        cpu_percent=cpu_percent,
                        memory_mb=memory.rss / (1024**2),
                        memory_percent=memory.rss / total_memory * 100,
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                self._processes.pop(pid, None)

        for stale_pid in self._processes.keys() - active_pids:
            self._processes.pop(stale_pid, None)
        readings.sort(key=lambda process: process.cpu_percent, reverse=True)
        return tuple(readings[:10])
