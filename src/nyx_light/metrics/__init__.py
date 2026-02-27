"""
Nyx Light — Prometheus Metrics

Izlaže metrike u Prometheus formatu na /metrics endpointu.
Kompatibilno s Grafana dashboardom.

Metrike:
  - nyx_requests_total (counter) — ukupan broj API poziva
  - nyx_request_duration_seconds (histogram) — latencija po endpointu
  - nyx_llm_tokens_total (counter) — ukupan broj generiranih tokena
  - nyx_llm_latency_seconds (histogram) — latencija LLM inference
  - nyx_memory_bytes (gauge) — Apple Silicon Unified Memory
  - nyx_active_sessions (gauge) — aktivne korisničke sesije
  - nyx_bookings_total (counter) — knjiženja po statusu
  - nyx_dpo_pairs_total (counter) — DPO trening parovi
  - nyx_errors_total (counter) — greške po tipu

Apple Silicon specifično:
  - nyx_silicon_memory_pressure (gauge) — memory pressure level (0-3)
  - nyx_silicon_gpu_utilization (gauge) — GPU/ANE utilizacija
  - nyx_silicon_thermal_state (gauge) — thermal throttle level
"""

import logging
import time
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger("nyx_light.metrics")


class Counter:
    """Prometheus-style counter."""
    def __init__(self, name: str, help_text: str, labels: list = None):
        self.name = name
        self.help_text = help_text
        self.labels = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)

    def inc(self, value: float = 1.0, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] += value

    def get(self, **label_values) -> float:
        key = tuple(label_values.get(l, "") for l in self.labels)
        return self._values[key]

    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        for key, val in self._values.items():
            if self.labels:
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key))
                lines.append(f"{self.name}{{{label_str}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


class Gauge:
    """Prometheus-style gauge."""
    def __init__(self, name: str, help_text: str, labels: list = None):
        self.name = name
        self.help_text = help_text
        self.labels = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)

    def set(self, value: float, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._values[key] = value

    def get(self, **label_values) -> float:
        key = tuple(label_values.get(l, "") for l in self.labels)
        return self._values[key]

    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        for key, val in self._values.items():
            if self.labels:
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key))
                lines.append(f"{self.name}{{{label_str}}} {val}")
            else:
                lines.append(f"{self.name} {val}")
        return "\n".join(lines)


class Histogram:
    """Prometheus-style histogram."""
    BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf")]

    def __init__(self, name: str, help_text: str, labels: list = None, buckets: list = None):
        self.name = name
        self.help_text = help_text
        self.labels = labels or []
        self.buckets = buckets or self.BUCKETS
        self._counts: Dict[tuple, Dict[float, int]] = defaultdict(lambda: defaultdict(int))
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._totals: Dict[tuple, int] = defaultdict(int)

    def observe(self, value: float, **label_values):
        key = tuple(label_values.get(l, "") for l in self.labels)
        self._sums[key] += value
        self._totals[key] += 1
        for bucket in self.buckets:
            if value <= bucket:
                self._counts[key][bucket] += 1

    def to_prometheus(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        for key in self._totals:
            if self.labels:
                label_str = ",".join(f'{l}="{v}"' for l, v in zip(self.labels, key))
                prefix = f"{self.name}{{{label_str}"
            else:
                label_str = ""
                prefix = self.name

            cumulative = 0
            for bucket in self.buckets:
                cumulative += self._counts[key].get(bucket, 0)
                le = "+Inf" if bucket == float("inf") else str(bucket)
                if self.labels:
                    lines.append(f'{self.name}_bucket{{{label_str},le="{le}"}} {cumulative}')
                else:
                    lines.append(f'{self.name}_bucket{{le="{le}"}} {cumulative}')

            if self.labels:
                lines.append(f"{self.name}_sum{{{label_str}}} {self._sums[key]}")
                lines.append(f"{self.name}_count{{{label_str}}} {self._totals[key]}")
            else:
                lines.append(f"{self.name}_sum {self._sums[key]}")
                lines.append(f"{self.name}_count {self._totals[key]}")
        return "\n".join(lines)


class PrometheusMetrics:
    """Centralizirani Prometheus metrics registry."""

    def __init__(self):
        self.requests_total = Counter("nyx_requests_total", "Total API requests", ["method", "endpoint", "status"])
        self.request_duration = Histogram("nyx_request_duration_seconds", "API request duration", ["endpoint"])
        self.llm_tokens_total = Counter("nyx_llm_tokens_total", "Total LLM tokens generated", ["model"])
        self.llm_latency = Histogram("nyx_llm_latency_seconds", "LLM inference latency", ["model"])
        self.memory_bytes = Gauge("nyx_memory_bytes", "Memory usage bytes", ["type"])
        self.active_sessions = Gauge("nyx_active_sessions", "Active user sessions")
        self.bookings_total = Counter("nyx_bookings_total", "Bookings by status", ["status"])
        self.dpo_pairs = Gauge("nyx_dpo_pairs_total", "DPO training pairs")
        self.errors_total = Counter("nyx_errors_total", "Errors by type", ["type"])

        # Apple Silicon specifično
        self.silicon_memory_pressure = Gauge("nyx_silicon_memory_pressure", "Memory pressure (0=nominal,1=warn,2=critical,3=fatal)")
        self.silicon_gpu_util = Gauge("nyx_silicon_gpu_utilization", "GPU/ANE utilization pct")
        self.silicon_thermal = Gauge("nyx_silicon_thermal_state", "Thermal state (0=nominal,1=fair,2=serious,3=critical)")

        self._all_metrics = [
            self.requests_total, self.request_duration,
            self.llm_tokens_total, self.llm_latency,
            self.memory_bytes, self.active_sessions,
            self.bookings_total, self.dpo_pairs, self.errors_total,
            self.silicon_memory_pressure, self.silicon_gpu_util, self.silicon_thermal,
        ]

        logger.info("PrometheusMetrics initialized")

    def export(self) -> str:
        """Export all metrics in Prometheus text format."""
        parts = []
        for m in self._all_metrics:
            text = m.to_prometheus()
            if text.strip() and text.count("\n") >= 2:  # Has actual data beyond help/type lines
                parts.append(text)
        return "\n\n".join(parts) + "\n"

    def update_silicon_stats(self):
        """Ažuriraj Apple Silicon metrike (macOS only)."""
        import subprocess
        import platform

        if platform.system() != "Darwin":
            return

        try:
            # Memory pressure
            result = subprocess.run(
                ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                self.silicon_memory_pressure.set(int(result.stdout.strip()))
        except Exception:
            pass

        try:
            # Thermal state
            result = subprocess.run(
                ["pmset", "-g", "therm"],
                capture_output=True, text=True, timeout=2,
            )
            if "CPU_Scheduler_Limit" in result.stdout:
                # Parse thermal level
                for line in result.stdout.splitlines():
                    if "CPU_Speed_Limit" in line:
                        speed = int(line.split("=")[-1].strip())
                        if speed >= 100:
                            self.silicon_thermal.set(0)
                        elif speed >= 80:
                            self.silicon_thermal.set(1)
                        elif speed >= 50:
                            self.silicon_thermal.set(2)
                        else:
                            self.silicon_thermal.set(3)
        except Exception:
            pass

        try:
            # Memory usage via vm_stat
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=2,
            )
            if result.returncode == 0:
                import re
                for line in result.stdout.splitlines():
                    if "Pages active" in line:
                        pages = int(re.search(r'(\d+)', line).group(1))
                        self.memory_bytes.set(pages * 16384, type="active")  # 16KB pages on Apple Silicon
                    elif "Pages wired" in line:
                        pages = int(re.search(r'(\d+)', line).group(1))
                        self.memory_bytes.set(pages * 16384, type="wired")
        except Exception:
            pass


# Singleton
metrics = PrometheusMetrics()
