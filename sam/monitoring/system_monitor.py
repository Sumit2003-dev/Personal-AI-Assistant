"""
SAM - Hardware & System Performance Monitoring
Real-time inspection and diagnostics for HP OMEN 16 (RTX 4050 6GB VRAM, 16GB RAM, Windows 11).
"""

from typing import Any
import subprocess
import psutil
from sam.tools.base import BaseTool, ToolResult
from sam.agent.models import RiskLevel
from sam.tools.registry import tool_registry


class SystemMonitor:
    """Inspects CPU, RAM, GPU (NVIDIA RTX 4050), and Disks."""

    @staticmethod
    def get_cpu_metrics() -> dict[str, Any]:
        return {
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "cpu_percent_overall": psutil.cpu_percent(interval=0.1),
            "cpu_percent_per_core": psutil.cpu_percent(interval=0.1, percpu=True),
        }

    @staticmethod
    def get_ram_metrics() -> dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "used_percent": mem.percent,
        }

    @staticmethod
    def get_gpu_metrics() -> dict[str, Any]:
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=gpu_name,driver_version,memory.total,memory.free,memory.used,temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits"
            ]
            raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
            parts = [p.strip() for p in raw.split(",")]
            if len(parts) >= 7:
                return {
                    "available": True,
                    "name": parts[0],
                    "driver_version": parts[1],
                    "vram_total_mb": int(parts[2]),
                    "vram_free_mb": int(parts[3]),
                    "vram_used_mb": int(parts[4]),
                    "temperature_c": float(parts[5]),
                    "gpu_util_percent": int(parts[6]),
                }
        except Exception:
            pass
        return {
            "available": False,
            "name": "NVIDIA GPU Telemetry Unavailable",
            "vram_total_mb": 0,
            "vram_free_mb": 0,
            "vram_used_mb": 0,
            "temperature_c": 0.0,
            "gpu_util_percent": 0,
        }

    @staticmethod
    def get_disk_metrics() -> list[dict[str, Any]]:
        disks = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "used_percent": usage.percent,
                })
            except Exception:
                continue
        return disks

    def get_full_telemetry(self) -> dict[str, Any]:
        return {
            "cpu": self.get_cpu_metrics(),
            "ram": self.get_ram_metrics(),
            "gpu": self.get_gpu_metrics(),
            "disks": self.get_disk_metrics(),
        }

    def analyze_health(self) -> dict[str, Any]:
        telemetry = self.get_full_telemetry()
        diagnostics = []
        recommendations = []
        overall_status = "HEALTHY"

        # Check Disks
        for disk in telemetry["disks"]:
            if disk["used_percent"] > 90.0:
                overall_status = "ATTENTION_REQUIRED"
                diagnostics.append(
                    f"CRITICAL DISK SPACE: Drive {disk['device']} is {disk['used_percent']}% full ({disk['free_gb']} GB free remaining)."
                )
                # Check if D: drive has plenty of space
                d_drive = next((d for d in telemetry["disks"] if "d:" in d["device"].lower()), None)
                if d_drive and d_drive["free_gb"] > 50:
                    recommendations.append(
                        f"Relocate large project workspaces, videos, and cache folders from C: to D: drive ({d_drive['free_gb']} GB free available)."
                    )

        # Check RAM
        ram = telemetry["ram"]
        if ram["used_percent"] > 85.0:
            overall_status = "ATTENTION_REQUIRED"
            diagnostics.append(f"HIGH RAM USAGE: {ram['used_percent']}% utilized ({ram['available_gb']} GB available).")
            recommendations.append("Close heavy background browser tabs or idle background IDE processes.")

        # Check GPU & VRAM
        gpu = telemetry["gpu"]
        if gpu.get("available"):
            if gpu["temperature_c"] > 82.0:
                overall_status = "ATTENTION_REQUIRED"
                diagnostics.append(f"HIGH GPU TEMPERATURE: {gpu['temperature_c']}°C on {gpu['name']}.")
                recommendations.append("Ensure HP OMEN 16 cooling vents are unobstructed and fan profile is optimized.")
            
            vram_free = gpu["vram_free_mb"]
            if vram_free < 1500:
                diagnostics.append(f"LOW VRAM HEADROOM: Only {vram_free} MB free on RTX 4050.")
                recommendations.append("Avoid loading heavy 3D rendering or secondary local LLMs simultaneously.")
            else:
                diagnostics.append(
                    f"GPU READY: {gpu['name']} has {vram_free} MB free VRAM ({round(vram_free/1024, 2)} GB) at {gpu['temperature_c']}°C. Optimal for Qwen3 4B."
                )

        if not diagnostics:
            diagnostics.append("All core systems (CPU, RAM, GPU, Disks) operating within optimal performance parameters.")

        return {
            "status": overall_status,
            "telemetry": telemetry,
            "diagnostics": diagnostics,
            "recommendations": recommendations,
        }


system_monitor = SystemMonitor()


# Tool Implementations
class SystemGetTelemetryTool(BaseTool):
    name = "system_get_telemetry"
    description = "Queries real-time hardware telemetry (CPU, RAM, GPU RTX 4050, and Disks) on HP OMEN 16."
    risk_level = RiskLevel.LOW

    def execute(self, **kwargs: Any) -> ToolResult:
        telemetry = system_monitor.get_full_telemetry()
        return ToolResult(success=True, output=telemetry)


class SystemAnalyzeHealthTool(BaseTool):
    name = "system_analyze_health"
    description = "Analyzes system performance, thermal status, memory headroom, and diagnoses hardware issues."
    risk_level = RiskLevel.LOW

    def execute(self, **kwargs: Any) -> ToolResult:
        health = system_monitor.analyze_health()
        return ToolResult(success=True, output=health)


# Auto-register tools
tool_registry.register(SystemGetTelemetryTool())
tool_registry.register(SystemAnalyzeHealthTool())

