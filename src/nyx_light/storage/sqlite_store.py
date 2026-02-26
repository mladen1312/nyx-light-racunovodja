"""
Nyx Light — SQLite Storage Backend

Lokalna baza podataka za:
- Knjiženja (proposals + odobrenj)
- Ispravci (corrections) za L2 memoriju
- Audit log (tko je što odobrio)
- Klijenti i dobavljači

Svi podaci 100% lokalno — NIKADA cloud.
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.storage")

DB_PATH = "data/memory_db/nyx_light.db"


class SQLiteStorage:
    """SQLite backend za Nyx Light."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = None
        self._init_db()
        logger.info("SQLiteStorage: %s", self.db_path)

    def _init_db(self):
        """Kreiraj tablice ako ne postoje."""
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS bookings (
                id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                document_type TEXT NOT NULL,
                konto_duguje TEXT,
                konto_potrazuje TEXT,
                iznos REAL NOT NULL DEFAULT 0,
                pdv_stopa REAL DEFAULT 25,
                pdv_iznos REAL DEFAULT 0,
                opis TEXT,
                oib TEXT,
                datum_dokumenta TEXT,
                datum_knjizenja TEXT,
                status TEXT DEFAULT 'pending',
                confidence REAL DEFAULT 0,
                ai_reasoning TEXT,
                approved_by TEXT,
                approved_at TEXT,
                erp_target TEXT DEFAULT 'CPP',
                exported INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id TEXT,
                user_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                original_konto TEXT,
                corrected_konto TEXT,
                document_type TEXT,
                supplier TEXT,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                user_id TEXT,
                booking_id TEXT,
                details TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS clients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                oib TEXT UNIQUE,
                erp_system TEXT DEFAULT 'CPP',
                active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                oib TEXT,
                iban TEXT,
                default_konto TEXT,
                client_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_bookings_client ON bookings(client_id);
            CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
            CREATE INDEX IF NOT EXISTS idx_corrections_client ON corrections(client_id);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
        """)
        self._conn.commit()

    def save_booking(self, booking: Dict[str, Any]) -> str:
        """Spremi prijedlog knjiženja."""
        booking_id = booking.get("id", f"bk_{int(time.time()*1000)}")
        self._conn.execute(
            """INSERT OR REPLACE INTO bookings
               (id, client_id, document_type, konto_duguje, konto_potrazuje,
                iznos, pdv_stopa, pdv_iznos, opis, oib,
                datum_dokumenta, datum_knjizenja, status, confidence,
                ai_reasoning, erp_target)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                booking_id,
                booking.get("client_id", ""),
                booking.get("document_type", ""),
                booking.get("konto_duguje", ""),
                booking.get("konto_potrazuje", ""),
                booking.get("iznos", 0),
                booking.get("pdv_stopa", 25),
                booking.get("pdv_iznos", 0),
                booking.get("opis", ""),
                booking.get("oib", ""),
                booking.get("datum_dokumenta", ""),
                booking.get("datum_knjizenja", ""),
                booking.get("status", "pending"),
                booking.get("confidence", 0),
                booking.get("ai_reasoning", ""),
                booking.get("erp_target", "CPP"),
            ),
        )
        self._conn.commit()
        return booking_id

    def approve_booking(self, booking_id: str, user_id: str) -> bool:
        """Odobri knjiženje (Human-in-the-Loop)."""
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            """UPDATE bookings SET status='approved', approved_by=?, approved_at=?, updated_at=?
               WHERE id=? AND status='pending'""",
            (user_id, now, now, booking_id),
        )
        self._conn.commit()

        if cursor.rowcount > 0:
            self._log_audit("approve_booking", user_id, booking_id)
            return True
        return False

    def reject_booking(self, booking_id: str, user_id: str, reason: str = "") -> bool:
        """Odbij knjiženje."""
        cursor = self._conn.execute(
            """UPDATE bookings SET status='rejected', updated_at=datetime('now')
               WHERE id=? AND status='pending'""",
            (booking_id,),
        )
        self._conn.commit()

        if cursor.rowcount > 0:
            self._log_audit("reject_booking", user_id, booking_id, reason)
            return True
        return False

    def save_correction(self, correction: Dict[str, Any]):
        """Spremi ispravak knjiženja — input za L2 memoriju."""
        self._conn.execute(
            """INSERT INTO corrections
               (booking_id, user_id, client_id, original_konto, corrected_konto,
                document_type, supplier, description)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                correction.get("booking_id", ""),
                correction.get("user_id", ""),
                correction.get("client_id", ""),
                correction.get("original_konto", ""),
                correction.get("corrected_konto", ""),
                correction.get("document_type", ""),
                correction.get("supplier", ""),
                correction.get("description", ""),
            ),
        )
        self._conn.commit()

    def get_pending_bookings(self, client_id: str = "") -> List[Dict]:
        """Dohvati knjiženja koja čekaju odobrenje."""
        if client_id:
            rows = self._conn.execute(
                "SELECT * FROM bookings WHERE status='pending' AND client_id=? ORDER BY created_at DESC",
                (client_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM bookings WHERE status='pending' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_approved_bookings(self, client_id: str = "", exported: bool = False) -> List[Dict]:
        """Dohvati odobrena knjiženja (za izvoz u ERP)."""
        query = "SELECT * FROM bookings WHERE status='approved'"
        params = []
        if client_id:
            query += " AND client_id=?"
            params.append(client_id)
        if not exported:
            query += " AND exported=0"
        query += " ORDER BY datum_knjizenja"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def mark_exported(self, booking_ids: List[str]):
        """Označi knjiženja kao izvezena u ERP."""
        placeholders = ",".join("?" for _ in booking_ids)
        self._conn.execute(
            f"UPDATE bookings SET exported=1, updated_at=datetime('now') WHERE id IN ({placeholders})",
            booking_ids,
        )
        self._conn.commit()

    def get_todays_corrections(self) -> List[Dict]:
        """Dohvati današnje ispravke (za Nightly DPO)."""
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._conn.execute(
            "SELECT * FROM corrections WHERE date(created_at)=?", (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    def _log_audit(self, action: str, user_id: str, booking_id: str = "", details: str = ""):
        """Zapiši u audit log."""
        self._conn.execute(
            "INSERT INTO audit_log (action, user_id, booking_id, details) VALUES (?, ?, ?, ?)",
            (action, user_id, booking_id, details),
        )
        self._conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        total = self._conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        pending = self._conn.execute("SELECT COUNT(*) FROM bookings WHERE status='pending'").fetchone()[0]
        approved = self._conn.execute("SELECT COUNT(*) FROM bookings WHERE status='approved'").fetchone()[0]
        corrections = self._conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0]
        return {
            "total_bookings": total,
            "pending": pending,
            "approved": approved,
            "corrections": corrections,
            "db_path": str(self.db_path),
        }

    def close(self):
        if self._conn:
            self._conn.close()
