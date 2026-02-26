"""
Nyx Light — System Monitoring

Prati zdravlje sustava na Mac Studio M5 Ultra:
- Unified Memory (iskorištenost, wired, swap)
- vLLM-MLX server status
- Qdrant/Neo4j status
- Inference latency
- Sesije i kapacitet
- Disk prostor

Izlaže metriku na /api/v1/monitor endpoint.
"""

import logging
import os
import platform
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.monitor")


class SystemMonitor:
    """Monitoring za Mac Studio M5 Ultra."""
    
    def __init__(self):
        self._inference_times: List[float] = []
        self._max_history = 1000
        self._alerts: List[Dict] = []
        self._start_time = datetime.now()
    
    def get_system_info(self) -> Dict[str, Any]:
        """Osnovne informacije o sustavu."""
        info = {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "uptime_hours": round((datetime.now() - self._start_time).total_seconds() / 3600, 2),
        }
        
        # macOS specifično
        if platform.system() == "Darwin":
            try:
                chip = subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    text=True, timeout=5
                ).strip()
                info["chip"] = chip
            except Exception:
                info["chip"] = "Unknown (macOS)"
            
            try:
                mem_bytes = int(subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True, timeout=5
                ).strip())
                info["total_memory_gb"] = round(mem_bytes / (1024**3), 1)
            except Exception:
                info["total_memory_gb"] = None
        
        return info
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Detaljna statistika memorije."""
        stats = {"available": True}
        
        if platform.system() != "Darwin":
            stats["available"] = False
            stats["note"] = "Memory monitoring requires macOS"
            return stats
        
        try:
            vm = subprocess.check_output(["vm_stat"], text=True, timeout=5)
            
            # Parse vm_stat
            page_size = 16384  # Apple Silicon default
            
            def extract_pages(label: str) -> int:
                for line in vm.split("\n"):
                    if label in line:
                        return int(line.split(":")[-1].strip().rstrip("."))
                return 0
            
            free = extract_pages("Pages free")
            active = extract_pages("Pages active")
            inactive = extract_pages("Pages inactive")
            wired = extract_pages("Pages wired")
            compressed = extract_pages("Pages occupied by compressor")
            
            total_pages = free + active + inactive + wired + compressed
            
            stats.update({
                "free_gb": round(free * page_size / (1024**3), 2),
                "active_gb": round(active * page_size / (1024**3), 2),
                "inactive_gb": round(inactive * page_size / (1024**3), 2),
                "wired_gb": round(wired * page_size / (1024**3), 2),
                "compressed_gb": round(compressed * page_size / (1024**3), 2),
                "used_pct": round((active + wired + compressed) / max(total_pages, 1) * 100, 1),
            })
            
            # Alert ako > 90%
            if stats["used_pct"] > 90:
                self._add_alert("memory_critical", f"Memory usage: {stats['used_pct']}%")
            
        except Exception as e:
            stats["error"] = str(e)
        
        return stats
    
    def get_disk_stats(self) -> Dict[str, Any]:
        """Disk prostor."""
        try:
            usage = os.statvfs("/")
            total_gb = (usage.f_blocks * usage.f_frsize) / (1024**3)
            free_gb = (usage.f_bavail * usage.f_frsize) / (1024**3)
            used_pct = round((1 - free_gb / total_gb) * 100, 1)
            
            stats = {
                "total_gb": round(total_gb, 1),
                "free_gb": round(free_gb, 1),
                "used_pct": used_pct,
            }
            
            if free_gb < 50:
                self._add_alert("disk_low", f"Disk free: {free_gb:.0f} GB")
            
            return stats
        except Exception as e:
            return {"error": str(e)}
    
    def check_vllm_status(self, host: str = "127.0.0.1", port: int = 8080) -> Dict[str, Any]:
        """Provjeri vLLM-MLX server."""
        try:
            import urllib.request
            url = f"http://{host}:{port}/v1/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {
                    "status": "running",
                    "port": port,
                    "response_code": resp.status,
                }
        except Exception as e:
            self._add_alert("vllm_down", f"vLLM-MLX nedostupan: {e}")
            return {"status": "offline", "port": port, "error": str(e)}
    
    def check_qdrant_status(self, url: str = "http://localhost:6333") -> Dict[str, Any]:
        """Provjeri Qdrant vektor bazu."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{url}/collections", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                import json
                data = json.loads(resp.read())
                collections = data.get("result", {}).get("collections", [])
                return {
                    "status": "running",
                    "collections": len(collections),
                    "url": url,
                }
        except Exception:
            return {"status": "offline", "url": url}
    
    def check_neo4j_status(self, url: str = "http://localhost:7474") -> Dict[str, Any]:
        """Provjeri Neo4j knowledge graph."""
        try:
            import urllib.request
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return {"status": "running", "url": url}
        except Exception:
            return {"status": "offline", "url": url}
    
    def record_inference(self, duration_ms: float):
        """Zabilježi trajanje inferencije."""
        self._inference_times.append(duration_ms)
        if len(self._inference_times) > self._max_history:
            self._inference_times = self._inference_times[-self._max_history:]
        
        if duration_ms > 10000:  # > 10s
            self._add_alert("slow_inference", f"Inference: {duration_ms:.0f}ms")
    
    def get_inference_stats(self) -> Dict[str, Any]:
        """Statistika inferencije."""
        if not self._inference_times:
            return {"count": 0}
        
        times = self._inference_times
        return {
            "count": len(times),
            "avg_ms": round(sum(times) / len(times), 1),
            "p50_ms": round(sorted(times)[len(times) // 2], 1),
            "p95_ms": round(sorted(times)[int(len(times) * 0.95)], 1),
            "max_ms": round(max(times), 1),
            "min_ms": round(min(times), 1),
        }
    
    def _add_alert(self, alert_type: str, message: str):
        """Dodaj alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        self._alerts.append(alert)
        # Zadrži zadnjih 100
        if len(self._alerts) > 100:
            self._alerts = self._alerts[-100:]
        logger.warning("⚠️  Alert: %s — %s", alert_type, message)
    
    def get_full_report(self) -> Dict[str, Any]:
        """Kompletni zdravstveni izvještaj."""
        return {
            "timestamp": datetime.now().isoformat(),
            "system": self.get_system_info(),
            "memory": self.get_memory_stats(),
            "disk": self.get_disk_stats(),
            "vllm": self.check_vllm_status(),
            "qdrant": self.check_qdrant_status(),
            "neo4j": self.check_neo4j_status(),
            "inference": self.get_inference_stats(),
            "alerts": self._alerts[-10:],  # Zadnjih 10
        }
