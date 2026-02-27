"""
Nyx Light — Email Watcher (IMAP)

Prati inbox za nove račune, izvode i dokumente.
Izvlači attachmente i šalje ih u upload pipeline.
"""

import asyncio
import email
import email.header
import email.utils
import imaplib
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("nyx_light.ingest.email")

SUPPORTED_EXTENSIONS = {
    ".pdf", ".xml", ".csv", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif",
    ".sta", ".mt940",
}


class EmailWatcher:
    """IMAP watcher za automatski prijem dokumenata emailom."""

    def __init__(
        self,
        imap_host: str = "",
        imap_port: int = 993,
        imap_user: str = "",
        imap_pass: str = "",
        check_interval: int = 120,
        folders: Optional[List[str]] = None,
        auto_archive: bool = True,
        archive_folder: str = "Nyx-Processed",
        upload_dir: str = "data/uploads/email",
    ):
        self.imap_host = imap_host
        self.imap_port = imap_port
        self.imap_user = imap_user
        self.imap_pass = imap_pass
        self.check_interval = check_interval
        self.folders = folders or ["INBOX"]
        self.auto_archive = auto_archive
        self.archive_folder = archive_folder
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._conn: Optional[imaplib.IMAP4_SSL] = None
        self._processed_uids: set = set()
        self._on_document: Optional[Callable] = None
        self._stats = {
            "emails_checked": 0, "attachments_saved": 0,
            "errors": 0, "last_check": None,
        }
        logger.info("EmailWatcher: %s@%s", imap_user or "(not configured)", imap_host)

    def set_document_callback(self, callback: Callable):
        self._on_document = callback

    async def start(self):
        if not self.imap_host or not self.imap_user:
            logger.warning("IMAP nije konfiguriran — email watcher neaktivan")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Email watcher pokrenut (interval: %ds)", self.check_interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._disconnect()

    async def _loop(self):
        while self._running:
            try:
                await asyncio.to_thread(self._check_all_folders)
                self._stats["last_check"] = datetime.now().isoformat()
            except Exception as e:
                self._stats["errors"] += 1
                logger.error("Email check error: %s", e)
                self._disconnect()
            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break

    def _connect(self) -> bool:
        try:
            self._conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            self._conn.login(self.imap_user, self.imap_pass)
            return True
        except Exception as e:
            logger.error("IMAP connect failed: %s", e)
            self._conn = None
            return False

    def _disconnect(self):
        if self._conn:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    def _check_all_folders(self):
        if not self._conn and not self._connect():
            return
        for folder in self.folders:
            try:
                self._check_folder(folder)
            except Exception as e:
                logger.error("Folder '%s' error: %s", folder, e)
                self._disconnect()
                break

    def _check_folder(self, folder: str):
        status, _ = self._conn.select(folder, readonly=not self.auto_archive)
        if status != "OK":
            return

        status, data = self._conn.search(None, "UNSEEN")
        if status != "OK":
            return

        uids = data[0].split()
        self._stats["emails_checked"] += len(uids)

        for uid in uids:
            uid_str = uid.decode()
            if uid_str in self._processed_uids:
                continue
            try:
                attachments = self._process_message(uid)
                if attachments:
                    self._processed_uids.add(uid_str)
                    if self.auto_archive:
                        self._archive_message(uid)
            except Exception as e:
                logger.error("UID %s error: %s", uid_str, e)

    def _process_message(self, uid: bytes) -> List[Dict]:
        status, data = self._conn.fetch(uid, "(RFC822)")
        if status != "OK":
            return []

        msg = email.message_from_bytes(data[0][1])
        from_addr = email.utils.parseaddr(msg.get("From", ""))[1]
        subject = self._decode_header(msg.get("Subject", ""))

        attachments = []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            filename = part.get_filename()
            if not filename:
                continue
            filename = self._decode_header(filename)
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            content = part.get_payload(decode=True)
            if not content:
                continue

            safe_name = re.sub(r'[^\w\-.]', '_', filename)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = self.upload_dir / f"{ts}_{safe_name}"
            save_path.write_bytes(content)

            meta = {
                "source": "email", "from": from_addr, "subject": subject,
                "filename": filename, "size_bytes": len(content), "extension": ext,
                "saved_to": str(save_path),
                "document_type": self._detect_type(filename, ext, content),
            }
            attachments.append(meta)
            self._stats["attachments_saved"] += 1

            if self._on_document:
                try:
                    self._on_document(str(save_path), meta)
                except Exception as e:
                    logger.error("Callback error: %s", e)

        return attachments

    def _detect_type(self, filename: str, ext: str, content: bytes) -> str:
        fn = filename.lower()
        if ext == ".xml":
            text = content[:2000].decode("utf-8", errors="ignore")
            if "Invoice" in text or "Račun" in text:
                return "e_racun"
            return "xml_document"
        if ext in (".sta", ".mt940"):
            return "bank_statement"
        if ext == ".csv":
            text = content[:500].decode("utf-8", errors="ignore")
            if any(kw in text.lower() for kw in ["iban", "iznos", "datum", "saldo"]):
                return "bank_statement"
            return "csv_data"
        if ext in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"):
            if any(kw in fn for kw in ["racun", "račun", "invoice", "faktura"]):
                return "invoice_scan"
            if any(kw in fn for kw in ["izvod", "statement"]):
                return "bank_statement"
            return "invoice_scan"
        return "unknown"

    def _archive_message(self, uid: bytes):
        try:
            self._conn.create(self.archive_folder)
        except Exception:
            pass
        try:
            self._conn.copy(uid, self.archive_folder)
            self._conn.store(uid, "+FLAGS", "\\Deleted")
            self._conn.expunge()
        except Exception as e:
            logger.warning("Archive failed: %s", e)

    @staticmethod
    def _decode_header(val: str) -> str:
        if not val:
            return ""
        parts = email.header.decode_header(val)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(part)
        return " ".join(decoded)

    async def check_now(self) -> Dict[str, Any]:
        try:
            await asyncio.to_thread(self._check_all_folders)
            return {"status": "ok", "stats": self._stats}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running, "configured": bool(self.imap_host)}
