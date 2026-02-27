"""
Nyx Light — Audit Trail

Centralizirano bilježenje svih akcija u sustavu za compliance.
Svaka promjena (knjiženje, odobrenje, ispravak, login) se logira
s vremenskim žigom, korisnikom i detaljima.

Zahtjevi:
  - Neizmjenjivost (append-only SQLite WAL)
  - Potpuna sljedivost (tko, kada, što, zašto)
  - Export za reviziju (Excel, CSV, JSON)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.audit")

# Re-export
from .export import AuditExporter


class AuditLogger:
    """Append-only audit trail za sve operacije."""

    def __init__(self, db_path: str = "data/audit.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")  # Append-only
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user TEXT NOT NULL DEFAULT 'system',
                client_id TEXT DEFAULT '',
                action TEXT NOT NULL,
                details TEXT DEFAULT '{}',
                ip_address TEXT DEFAULT '',
                session_id TEXT DEFAULT '',
                booking_id TEXT DEFAULT '',
                severity TEXT DEFAULT 'info'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_log(event_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user)
        """)
        conn.commit()
        conn.close()

    def log(self, event_type: str, action: str, user: str = "system",
            client_id: str = "", details: Optional[Dict] = None,
            ip_address: str = "", session_id: str = "",
            booking_id: str = "", severity: str = "info"):
        """Zapiši audit event."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT INTO audit_log
               (timestamp, event_type, user, client_id, action, details,
                ip_address, session_id, booking_id, severity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                event_type, user, client_id, action,
                json.dumps(details or {}, ensure_ascii=False),
                ip_address, session_id, booking_id, severity,
            )
        )
        conn.commit()
        conn.close()

    def log_login(self, user: str, ip: str = "", success: bool = True):
        self.log("auth", "login_success" if success else "login_failed",
                 user=user, ip_address=ip,
                 severity="info" if success else "warning")

    def log_booking(self, user: str, booking_id: str, action: str,
                    client_id: str = "", details: Optional[Dict] = None):
        self.log("booking", action, user=user, client_id=client_id,
                 booking_id=booking_id, details=details)

    def log_approval(self, user: str, booking_id: str, approved: bool,
                     reason: str = ""):
        self.log("approval", "approved" if approved else "rejected",
                 user=user, booking_id=booking_id,
                 details={"reason": reason},
                 severity="info" if approved else "warning")

    def log_correction(self, user: str, booking_id: str, changes: Dict):
        self.log("correction", "booking_corrected", user=user,
                 booking_id=booking_id, details=changes, severity="warning")

    def log_export(self, user: str, export_type: str, client_id: str = ""):
        self.log("export", f"export_{export_type}", user=user, client_id=client_id)

    def log_security(self, action: str, user: str = "", details: Optional[Dict] = None):
        self.log("security", action, user=user, details=details, severity="critical")

    def query(self, event_type: str = "", user: str = "",
              date_from: str = "", date_to: str = "",
              severity: str = "", limit: int = 100,
              offset: int = 0) -> List[Dict]:
        """Pretraži audit log."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        conditions = []
        params = []

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if user:
            conditions.append("user = ?")
            params.append(user)
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to)
        if severity:
            conditions.append("severity = ?")
            params.append(severity)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()
        conn.close()

        return [dict(r) for r in rows]

    def count(self, event_type: str = "", date_from: str = "", date_to: str = "") -> int:
        conn = sqlite3.connect(str(self.db_path))
        conditions = []
        params = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        result = conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()
        conn.close()
        return result[0]

    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        types = conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM audit_log GROUP BY event_type"
        ).fetchall()
        conn.close()
        return {
            "total_entries": total,
            "by_type": {t[0]: t[1] for t in types},
            "db_path": str(self.db_path),
        }
