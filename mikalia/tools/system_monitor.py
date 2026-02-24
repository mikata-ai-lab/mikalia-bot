"""
system_monitor.py — Mikalia se monitorea a si misma.

Reporta CPU, RAM, disco y uptime del sistema donde corre.
Util para el VPS y para el daily brief.
No requiere dependencias externas (usa stdlib).
"""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.system_monitor")

_boot_time: float | None = None


def _get_boot_time() -> float:
    """Obtiene el tiempo de inicio del proceso."""
    global _boot_time
    if _boot_time is None:
        _boot_time = time.time()
    return _boot_time


class SystemMonitorTool(BaseTool):
    """Monitorea recursos del sistema: CPU, RAM, disco, uptime."""

    @property
    def name(self) -> str:
        return "system_monitor"

    @property
    def description(self) -> str:
        return (
            "Monitor system resources: CPU usage, memory usage, disk space, "
            "uptime, and OS info. Use this to check if the server is healthy "
            "or to include system stats in reports."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_disk": {
                    "type": "boolean",
                    "description": "Include disk usage info (default: true)",
                },
            },
            "required": [],
        }

    def execute(self, include_disk: bool = True, **_: Any) -> ToolResult:
        lines = []

        # OS Info
        lines.append("=== System Info ===")
        lines.append(f"OS: {platform.system()} {platform.release()}")
        lines.append(f"Machine: {platform.machine()}")
        lines.append(f"Python: {platform.python_version()}")
        lines.append(f"PID: {os.getpid()}")

        # Uptime
        uptime_secs = int(time.time() - _get_boot_time())
        hours, remainder = divmod(uptime_secs, 3600)
        mins, secs = divmod(remainder, 60)
        lines.append(f"Process uptime: {hours}h {mins}m {secs}s")

        # Memory (cross-platform via /proc or psutil-free approach)
        mem_info = self._get_memory_info()
        if mem_info:
            lines.append("")
            lines.append("=== Memory ===")
            for k, v in mem_info.items():
                lines.append(f"{k}: {v}")

        # CPU
        cpu_info = self._get_cpu_info()
        if cpu_info:
            lines.append("")
            lines.append("=== CPU ===")
            for k, v in cpu_info.items():
                lines.append(f"{k}: {v}")

        # Disk
        if include_disk:
            disk_info = self._get_disk_info()
            if disk_info:
                lines.append("")
                lines.append("=== Disk ===")
                for k, v in disk_info.items():
                    lines.append(f"{k}: {v}")

        # Mikalia-specific
        lines.append("")
        lines.append("=== Mikalia ===")
        db_path = Path("data/mikalia.db")
        if db_path.exists():
            db_size = db_path.stat().st_size
            lines.append(f"DB size: {db_size / 1024:.1f} KB")

        log_path = Path("logs/mikalia.log")
        if log_path.exists():
            log_size = log_path.stat().st_size
            lines.append(f"Log size: {log_size / 1024:.1f} KB")

        return ToolResult(success=True, output="\n".join(lines))

    def _get_memory_info(self) -> dict[str, str]:
        """Obtiene info de memoria (cross-platform)."""
        info = {}
        try:
            if platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    meminfo = f.read()
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1]) / 1024
                        info["Total"] = f"{total:.0f} MB"
                    elif line.startswith("MemAvailable:"):
                        avail = int(line.split()[1]) / 1024
                        info["Available"] = f"{avail:.0f} MB"
                if "Total" in info and "Available" in info:
                    total_mb = float(info["Total"].split()[0])
                    avail_mb = float(info["Available"].split()[0])
                    used_pct = (1 - avail_mb / total_mb) * 100
                    info["Used"] = f"{used_pct:.1f}%"
            elif platform.system() == "Windows":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                c_ulonglong = ctypes.c_ulonglong

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", c_ulonglong),
                        ("ullAvailPhys", c_ulonglong),
                        ("ullTotalPageFile", c_ulonglong),
                        ("ullAvailPageFile", c_ulonglong),
                        ("ullTotalVirtual", c_ulonglong),
                        ("ullAvailVirtual", c_ulonglong),
                        ("ullAvailExtendedVirtual", c_ulonglong),
                    ]

                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                info["Total"] = f"{stat.ullTotalPhys / (1024**2):.0f} MB"
                info["Available"] = f"{stat.ullAvailPhys / (1024**2):.0f} MB"
                info["Used"] = f"{stat.dwMemoryLoad}%"
        except Exception:
            info["Status"] = "Unable to read memory info"
        return info

    def _get_cpu_info(self) -> dict[str, str]:
        """Obtiene info de CPU."""
        info = {}
        info["Cores"] = str(os.cpu_count() or "unknown")
        try:
            if platform.system() == "Linux":
                with open("/proc/loadavg") as f:
                    load = f.read().split()
                info["Load avg (1/5/15m)"] = f"{load[0]} / {load[1]} / {load[2]}"
        except Exception:
            pass
        return info

    def _get_disk_info(self) -> dict[str, str]:
        """Obtiene info de disco."""
        info = {}
        try:
            import shutil
            usage = shutil.disk_usage(".")
            info["Total"] = f"{usage.total / (1024**3):.1f} GB"
            info["Used"] = f"{usage.used / (1024**3):.1f} GB"
            info["Free"] = f"{usage.free / (1024**3):.1f} GB"
            info["Usage"] = f"{usage.used / usage.total * 100:.1f}%"
        except Exception:
            info["Status"] = "Unable to read disk info"
        return info
