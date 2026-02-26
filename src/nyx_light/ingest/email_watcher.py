"""
Email Watcher — IMAP nadzor za automatski prijem dokumenata.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.ingest.email")


class EmailWatcher:
    """IMAP watcher za automatski prijem računa/izvoda emailom."""

    def __init__(self, imap_host: str = "", imap_user: str = "", imap_pass: str = ""):
        self.imap_host = imap_host
        self.imap_user = imap_user
        self._running = False
        logger.info("EmailWatcher konfiguriran za %s", imap_host or "(nije konfigurirano)")

    async def start(self):
        """Pokreni IMAP monitoring."""
        if not self.imap_host:
            logger.warning("IMAP nije konfiguriran — email watcher neaktivan")
            return
        self._running = True
        logger.info("Email watcher pokrenut")

    async def stop(self):
        self._running = False
