"""
Modul: Double-Entry Ledger (Dvojno Knjigovodstvo)
═══════════════════════════════════════════════════
Striktni double-entry sustav s invariantima:
  1. Svaka transakcija: SUM(duguje) == SUM(potražuje)
  2. Nijedan unos ne može narušiti ravnotežu
  3. Immutable audit trail — jednom proknjiženo, ne briše se (samo storno)
"""

import hashlib
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.ledger")

PRECISION = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(PRECISION, rounding=ROUND_HALF_UP)
    try:
        d = Decimal(str(value))
        if d.is_nan() or d.is_infinite():
            raise ValueError(f"Nedozvoljeni iznos: {value}")
        return d.quantize(PRECISION, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"Neispravan iznos '{value}': {e}")


class Strana(str, Enum):
    DUGUJE = "duguje"
    POTRAZUJE = "potrazuje"


class StatusKnjizenja(str, Enum):
    PRIJEDLOG = "prijedlog"
    ODOBRENO = "odobreno"
    PROKNJIZENO = "proknjizeno"
    STORNIRANO = "stornirano"


@dataclass
class LedgerEntry:
    konto: str
    strana: Strana
    iznos: Decimal
    opis: str = ""
    partner_oib: str = ""
    cost_center: str = ""

    def __post_init__(self):
        self.iznos = to_decimal(self.iznos)
        if self.iznos < ZERO:
            raise ValueError(f"Iznos ne smije biti negativan: {self.iznos}")
        if not self.konto or len(self.konto) < 3:
            raise ValueError(f"Konto mora imati barem 3 znamenke: '{self.konto}'")
        if isinstance(self.strana, str):
            self.strana = Strana(self.strana.lower())


@dataclass
class Transaction:
    datum: str
    opis: str
    entries: List[LedgerEntry]
    document_ref: str = ""
    client_id: str = ""
    created_by: str = ""
    source: str = "manual"
    status: StatusKnjizenja = StatusKnjizenja.PRIJEDLOG
    tx_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_duguje(self) -> Decimal:
        return sum((e.iznos for e in self.entries if e.strana == Strana.DUGUJE), ZERO)

    @property
    def total_potrazuje(self) -> Decimal:
        return sum((e.iznos for e in self.entries if e.strana == Strana.POTRAZUJE), ZERO)

    @property
    def is_balanced(self) -> bool:
        return self.total_duguje == self.total_potrazuje

    @property
    def balance_diff(self) -> Decimal:
        return self.total_duguje - self.total_potrazuje

    def validate(self) -> List[str]:
        errors = []
        if not self.entries:
            errors.append("Transakcija mora imati barem jednu stavku")
        if len(self.entries) < 2:
            errors.append("Double-entry zahtijeva min 2 stavke (duguje + potražuje)")
        if not self.is_balanced:
            errors.append(
                f"NERAVNOTEŽA: duguje={self.total_duguje} "
                f"potražuje={self.total_potrazuje} razlika={self.balance_diff}")
        if not self.datum:
            errors.append("Datum je obavezan")
        if not self.opis:
            errors.append("Opis transakcije je obavezan")
        has_d = any(e.strana == Strana.DUGUJE for e in self.entries)
        has_p = any(e.strana == Strana.POTRAZUJE for e in self.entries)
        if not has_d:
            errors.append("Nema stavke na dugovnoj strani")
        if not has_p:
            errors.append("Nema stavke na potražnoj strani")
        for i, e in enumerate(self.entries):
            if e.iznos == ZERO:
                errors.append(f"Stavka {i+1}: iznos ne smije biti 0.00")
        return errors

    def fingerprint(self) -> str:
        parts = [self.tx_id, self.datum, self.opis, self.document_ref]
        for e in sorted(self.entries, key=lambda x: (x.konto, x.strana.value)):
            parts.extend([e.konto, e.strana.value, str(e.iznos)])
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


class BalanceError(Exception):
    pass


class GeneralLedger:
    def __init__(self, db_path: str = ":memory:"):
        self._lock = threading.Lock()
        self._tx_count = 0
        self._storno_count = 0
        self._rejected_count = 0
        self._transactions: List[Transaction] = []
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        c = self._conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY, datum TEXT NOT NULL, opis TEXT NOT NULL,
                document_ref TEXT DEFAULT '', client_id TEXT DEFAULT '',
                created_by TEXT DEFAULT '', source TEXT DEFAULT 'manual',
                status TEXT DEFAULT 'prijedlog', total_duguje TEXT NOT NULL,
                total_potrazuje TEXT NOT NULL, fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL, metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS ledger_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT NOT NULL, konto TEXT NOT NULL,
                strana TEXT NOT NULL CHECK(strana IN ('duguje', 'potrazuje')),
                iznos TEXT NOT NULL, opis TEXT DEFAULT '',
                partner_oib TEXT DEFAULT '', cost_center TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_entries_konto ON ledger_entries(konto);
            CREATE INDEX IF NOT EXISTS idx_tx_datum ON transactions(datum);
            CREATE INDEX IF NOT EXISTS idx_tx_status ON transactions(status);
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, action TEXT, tx_id TEXT,
                user_id TEXT DEFAULT '', details TEXT DEFAULT '',
                fingerprint TEXT DEFAULT ''
            );
        """)
        c.commit()

    def book(self, tx: Transaction, user: str = "") -> Transaction:
        errors = tx.validate()
        if errors:
            self._rejected_count += 1
            if not tx.is_balanced:
                raise BalanceError(f"ODBIJENO — neuravnotežena: {'; '.join(errors)}")
            raise ValueError(f"Validacijske greške: {'; '.join(errors)}")
        tx.status = StatusKnjizenja.PROKNJIZENO
        tx.created_by = user or tx.created_by or "system"
        fp = tx.fingerprint()
        with self._lock:
            c = self._conn
            c.execute(
                "INSERT INTO transactions (tx_id,datum,opis,document_ref,client_id,created_by,"
                "source,status,total_duguje,total_potrazuje,fingerprint,created_at,metadata) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tx.tx_id, tx.datum, tx.opis, tx.document_ref, tx.client_id,
                 tx.created_by, tx.source, tx.status.value,
                 str(tx.total_duguje), str(tx.total_potrazuje),
                 fp, tx.created_at, str(tx.metadata)))
            for e in tx.entries:
                c.execute(
                    "INSERT INTO ledger_entries (tx_id,konto,strana,iznos,opis,partner_oib,cost_center) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (tx.tx_id, e.konto, e.strana.value, str(e.iznos),
                     e.opis, e.partner_oib, e.cost_center))
            c.execute(
                "INSERT INTO audit_log (timestamp,action,tx_id,user_id,details,fingerprint) "
                "VALUES (?,?,?,?,?,?)",
                (datetime.now().isoformat(), "BOOK", tx.tx_id, tx.created_by, tx.opis, fp))
            c.commit()
            self._transactions.append(tx)
            self._tx_count += 1
        return tx

    def propose(self, tx: Transaction) -> Transaction:
        errors = tx.validate()
        if errors:
            raise ValueError(f"Prijedlog neispravan: {'; '.join(errors)}")
        tx.status = StatusKnjizenja.PRIJEDLOG
        tx.source = "ai_proposed"
        self._transactions.append(tx)
        return tx

    def approve(self, tx_id: str, user: str) -> Transaction:
        for tx in self._transactions:
            if tx.tx_id == tx_id and tx.status == StatusKnjizenja.PRIJEDLOG:
                tx.status = StatusKnjizenja.ODOBRENO
                return self.book(tx, user=user)
        raise ValueError(f"Transakcija {tx_id} nije pronađena ili nije prijedlog")

    def storno(self, tx_id: str, user: str, razlog: str = "") -> Transaction:
        original = None
        for tx in self._transactions:
            if tx.tx_id == tx_id and tx.status == StatusKnjizenja.PROKNJIZENO:
                original = tx
                break
        if not original:
            raise ValueError(f"Transakcija {tx_id} ne postoji ili nije proknjižena")
        storno_entries = []
        for e in original.entries:
            new_strana = Strana.POTRAZUJE if e.strana == Strana.DUGUJE else Strana.DUGUJE
            storno_entries.append(LedgerEntry(
                konto=e.konto, strana=new_strana, iznos=e.iznos,
                opis=f"STORNO: {e.opis}", partner_oib=e.partner_oib))
        storno_tx = Transaction(
            datum=date.today().isoformat(),
            opis=f"STORNO #{original.tx_id}: {razlog or original.opis}",
            entries=storno_entries, document_ref=f"STORNO-{original.document_ref}",
            client_id=original.client_id, source="storno")
        original.status = StatusKnjizenja.STORNIRANO
        self._storno_count += 1
        with self._lock:
            self._conn.execute("UPDATE transactions SET status=? WHERE tx_id=?",
                               (StatusKnjizenja.STORNIRANO.value, tx_id))
            self._conn.commit()
        return self.book(storno_tx, user=user)

    def trial_balance(self, datum_do: str = "") -> Dict[str, Any]:
        saldos = {}
        total_d, total_p = ZERO, ZERO
        query = ("SELECT e.konto, e.strana, SUM(CAST(e.iznos AS REAL)) "
                 "FROM ledger_entries e JOIN transactions t ON e.tx_id = t.tx_id "
                 "WHERE t.status = 'proknjizeno'")
        params: list = []
        if datum_do:
            query += " AND t.datum <= ?"
            params.append(datum_do)
        query += " GROUP BY e.konto, e.strana ORDER BY e.konto"
        for konto, strana, iznos in self._conn.execute(query, params):
            if konto not in saldos:
                saldos[konto] = {"duguje": ZERO, "potrazuje": ZERO}
            d = to_decimal(iznos)
            if strana == "duguje":
                saldos[konto]["duguje"] += d
                total_d += d
            else:
                saldos[konto]["potrazuje"] += d
                total_p += d
        return {
            "konta": {k: {**v, "saldo": v["duguje"] - v["potrazuje"]}
                      for k, v in sorted(saldos.items())},
            "total_duguje": total_d, "total_potrazuje": total_p,
            "balanced": total_d == total_p, "difference": total_d - total_p,
        }

    def verify_integrity(self) -> Dict[str, Any]:
        issues = []
        total_d, total_p = ZERO, ZERO
        for row in self._conn.execute(
            "SELECT tx_id, total_duguje, total_potrazuje FROM transactions WHERE status='proknjizeno'"
        ):
            d, p = to_decimal(row[1]), to_decimal(row[2])
            if d != p:
                issues.append(f"TX {row[0]}: D={d} P={p}")
            total_d += d
            total_p += p
        return {"total_transactions": self._tx_count,
                "total_duguje": total_d, "total_potrazuje": total_p,
                "global_balance": total_d == total_p,
                "issues": issues, "integrity_ok": len(issues) == 0}

    def get_stats(self) -> Dict[str, Any]:
        return {"module": "ledger", "transactions": self._tx_count,
                "storno": self._storno_count, "rejected": self._rejected_count,
                "integrity": self.verify_integrity()["integrity_ok"]}
