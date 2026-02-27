"""
Nyx Light — Scheduler (Noćni zadaci)

Automatski pokreće noćne zadatke:
  - 02:00 — Nightly DPO training
  - 03:00 — Automatski backup
  - 04:00 — Provjera ažuriranja zakona
  - 05:00 — Čišćenje starih log-ova
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nyx_light.scheduler")


class ScheduledTask:
    def __init__(self, name: str, hour: int, minute: int = 0,
                 func: Optional[Callable] = None, enabled: bool = True):
        self.name = name
        self.hour = hour
        self.minute = minute
        self.func = func
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[Dict] = None
        self.run_count = 0
        self.error_count = 0

    def should_run(self, now: datetime) -> bool:
        if not self.enabled or not self.func:
            return False
        if now.hour == self.hour and now.minute == self.minute:
            if self.last_run is None or self.last_run.date() < now.date():
                return True
        return False


class NyxScheduler:
    """Scheduler za noćne zadatke."""

    def __init__(self):
        self.tasks: List[ScheduledTask] = []
        self._running = False
        self._check_interval = 30  # Check every 30 seconds

    def add_task(self, name: str, hour: int, minute: int = 0,
                 func: Callable = None, enabled: bool = True):
        task = ScheduledTask(name, hour, minute, func, enabled)
        self.tasks.append(task)
        logger.info("Zakazan zadatak: %s @ %02d:%02d", name, hour, minute)

    async def start(self):
        """Pokreni scheduler loop."""
        self._running = True
        logger.info("Scheduler pokrenut (%d zadataka)", len(self.tasks))
        while self._running:
            now = datetime.now()
            for task in self.tasks:
                if task.should_run(now):
                    await self._execute_task(task)
            await asyncio.sleep(self._check_interval)

    def stop(self):
        self._running = False
        logger.info("Scheduler zaustavljen")

    async def _execute_task(self, task: ScheduledTask):
        logger.info("Pokrećem zadatak: %s", task.name)
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(task.func):
                result = await task.func()
            else:
                result = task.func()
            task.last_result = result if isinstance(result, dict) else {"result": str(result)}
            task.run_count += 1
            duration = time.time() - start
            logger.info("Zadatak %s završen za %.1fs: %s", task.name, duration, result)
        except Exception as e:
            task.error_count += 1
            task.last_result = {"error": str(e)}
            logger.error("Zadatak %s greška: %s", task.name, e)
        task.last_run = datetime.now()

    async def run_task_now(self, task_name: str) -> Dict:
        """Ručno pokretanje zadatka."""
        for task in self.tasks:
            if task.name == task_name:
                await self._execute_task(task)
                return task.last_result or {}
        return {"error": f"Zadatak '{task_name}' ne postoji"}

    def get_stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "tasks": [
                {
                    "name": t.name,
                    "schedule": f"{t.hour:02d}:{t.minute:02d}",
                    "enabled": t.enabled,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                }
                for t in self.tasks
            ],
        }


def setup_default_scheduler(dpo_trainer=None, backup_manager=None) -> NyxScheduler:
    """Kreiraj scheduler s default noćnim zadacima."""
    scheduler = NyxScheduler()

    if dpo_trainer:
        scheduler.add_task("nightly_dpo", hour=2, minute=0,
                          func=dpo_trainer.train_nightly)

    if backup_manager:
        scheduler.add_task("nightly_backup", hour=3, minute=0,
                          func=lambda: backup_manager.create_backup("nightly"))

    # Cleanup old logs
    def cleanup_logs():
        log_dir = Path("data/logs")
        cutoff = datetime.now() - timedelta(days=90)
        removed = 0
        for f in log_dir.glob("*.log.*"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                removed += 1
        return {"removed_logs": removed}

    scheduler.add_task("cleanup_logs", hour=5, minute=0, func=cleanup_logs)

    return scheduler
