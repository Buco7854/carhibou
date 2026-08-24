import os
import platform
from collections.abc import Callable
from pathlib import Path


class LinuxSystemHealthProvider:
    def __init__(self, queue_depth: Callable[[], int] | None = None):
        self.queue_depth = queue_depth

    def read_health(self) -> dict[str, object]:
        load = os.getloadavg()[0] if hasattr(os, "getloadavg") else None
        temperature = self._cpu_temperature()
        result: dict[str, object] = {
            "hostname": platform.node(),
            "load_1m": load,
        }
        if temperature is not None:
            result["cpu_temperature"] = temperature
        if self.queue_depth:
            result["queue_depth"] = self.queue_depth()
        return result

    @staticmethod
    def _cpu_temperature() -> float | None:
        path = Path("/sys/class/thermal/thermal_zone0/temp")
        try:
            return round(int(path.read_text().strip()) / 1000, 1)
        except (OSError, ValueError):
            return None
