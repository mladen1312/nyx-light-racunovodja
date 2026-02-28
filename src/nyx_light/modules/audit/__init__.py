"""
Modul: Audit Trail & Anomaly Detection
═══════════════════════════════════════
1. Immutable audit trail s chain hashovima
2. Anomaly detection — duplikati, Benford, IBAN promjene, AML
3. GDPR data masking
"""

import hashlib
import logging
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nyx_light.audit")


class AkcijaTip(str, Enum):
    KNJIZENJE = "knjizenje"
    STORNO = "storno"
    ODOBRENJE = "odobrenje"
    ODBIJANJE = "odbijanje"
    PROMJENA = "promjena"
    LOGIN = "login"
    EXPORT = "export"
    AI_PRIJEDLOG = "ai_prijedlog"
    AI_KOREKCIJA = "ai_korekcija"
    FISKALIZACIJA = "fiskalizacija"
    PREGLED = "pregled"


class RizikRazina(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    timestamp: str
    user_id: str
    action: AkcijaTip
    module: str
    details: str
    entity_id: str = ""
    client_id: str = ""
    ip_address: str = ""
    risk_level: RizikRazina = RizikRazina.LOW
    fingerprint: str = ""

    def __post_init__(self):
        if not self.fingerprint:
            raw = f"{self.timestamp}|{self.user_id}|{self.action}|{self.details}"
            self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:16]


class AuditTrail:
    """Immutable chain-linked audit trail — COSO kompatibilan."""

    def __init__(self, db_path: str = ":memory:"):
        self._lock = threading.Lock()
        self._count = 0
        self._chain_hash = "GENESIS"
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, user_id TEXT NOT NULL,
                action TEXT NOT NULL, module TEXT DEFAULT '',
                details TEXT DEFAULT '', entity_id TEXT DEFAULT '',
                client_id TEXT DEFAULT '', ip_address TEXT DEFAULT '',
                risk_level TEXT DEFAULT 'low',
                fingerprint TEXT NOT NULL, chain_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_trail(user_id);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_trail(action);
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_trail(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_risk ON audit_trail(risk_level);
        """)
        self._conn.commit()

    def log(self, user_id: str, action: AkcijaTip, module: str,
            details: str, entity_id: str = "", client_id: str = "",
            risk_level: RizikRazina = RizikRazina.LOW) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(), user_id=user_id,
            action=action, module=module, details=details,
            entity_id=entity_id, client_id=client_id, risk_level=risk_level,
        )
        chain_raw = f"{self._chain_hash}|{entry.fingerprint}"
        new_chain = hashlib.sha256(chain_raw.encode()).hexdigest()[:16]

        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_trail "
                "(timestamp,user_id,action,module,details,entity_id,"
                "client_id,ip_address,risk_level,fingerprint,chain_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (entry.timestamp, entry.user_id, entry.action.value,
                 entry.module, entry.details, entry.entity_id,
                 entry.client_id, entry.ip_address, entry.risk_level.value,
                 entry.fingerprint, new_chain))
            self._conn.commit()
            self._chain_hash = new_chain
            self._count += 1
        return entry

    def verify_chain(self) -> Dict[str, Any]:
        rows = self._conn.execute(
            "SELECT fingerprint, chain_hash FROM audit_trail ORDER BY id"
        ).fetchall()
        if not rows:
            return {"valid": True, "entries": 0, "breaks": []}
        prev_hash = "GENESIS"
        breaks = []
        for i, (fp, chain) in enumerate(rows):
            expected = hashlib.sha256(f"{prev_hash}|{fp}".encode()).hexdigest()[:16]
            if chain != expected:
                breaks.append({"position": i, "expected": expected, "found": chain})
            prev_hash = chain
        return {"valid": len(breaks) == 0, "entries": len(rows), "breaks": breaks}

    def query(self, user_id: str = "", action: str = "",
              from_date: str = "", to_date: str = "",
              risk_level: str = "", limit: int = 100) -> List[Dict]:
        query = "SELECT * FROM audit_trail WHERE 1=1"
        params: list = []
        if user_id:
            query += " AND user_id = ?"; params.append(user_id)
        if action:
            query += " AND action = ?"; params.append(action)
        if from_date:
            query += " AND timestamp >= ?"; params.append(from_date)
        if to_date:
            query += " AND timestamp <= ?"; params.append(to_date)
        if risk_level:
            query += " AND risk_level = ?"; params.append(risk_level)
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        rows = self._conn.execute(query, params).fetchall()
        return [{"id": r[0], "timestamp": r[1], "user_id": r[2],
                 "action": r[3], "module": r[4], "details": r[5],
                 "entity_id": r[6], "risk_level": r[9]} for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        return {"module": "audit_trail", "entries": self._count,
                "chain_valid": self.verify_chain()["valid"]}


# ═══════════════════════════════════════════════
# ANOMALY DETECTION
# ═══════════════════════════════════════════════

@dataclass
class Anomaly:
    tip: str
    razina: RizikRazina
    opis: str
    entity_id: str = ""
    iznos: float = 0.0
    preporuka: str = ""


class AnomalyDetector:
    """Detekcija anomalija: duplikati, Benford, IBAN promjene, AML."""

    def __init__(self):
        self._history: List[Dict] = []
        self._partner_ibans: Dict[str, Set[str]] = defaultdict(set)
        self._detections = 0

    def check_transaction(self, iznos: float = 0, partner_oib: str = "",
                          partner_iban: str = "", datum: str = "",
                          opis: str = "", user_id: str = "",
                          konto: str = "") -> List[Anomaly]:
        anomalies = []
        dup = self._check_duplicate(iznos, partner_oib, datum)
        if dup:
            anomalies.append(dup)
        anomalies.extend(self._check_amount(iznos, konto))
        if partner_oib and partner_iban:
            iban_check = self._check_iban_change(partner_oib, partner_iban)
            if iban_check:
                anomalies.append(iban_check)
        time_check = self._check_timing(datum)
        if time_check:
            anomalies.append(time_check)
        self._history.append({"iznos": iznos, "partner_oib": partner_oib,
                              "datum": datum, "opis": opis, "konto": konto})
        if partner_oib and partner_iban:
            self._partner_ibans[partner_oib].add(partner_iban)
        self._detections += len(anomalies)
        return anomalies

    def check_batch(self, transactions: List[Dict]) -> Dict[str, Any]:
        all_anomalies = []
        for tx in transactions:
            anoms = self.check_transaction(
                iznos=tx.get("iznos", 0), partner_oib=tx.get("partner_oib", ""),
                partner_iban=tx.get("partner_iban", ""), datum=tx.get("datum", ""),
                opis=tx.get("opis", ""), konto=tx.get("konto", ""))
            all_anomalies.extend(anoms)
        benford = self._benford_test([tx.get("iznos", 0) for tx in transactions])
        return {
            "total_checked": len(transactions),
            "anomalies_found": len(all_anomalies),
            "anomalies": [{"tip": a.tip, "razina": a.razina.value,
                           "opis": a.opis, "iznos": a.iznos,
                           "preporuka": a.preporuka} for a in all_anomalies],
            "benford_analysis": benford,
            "risk_summary": self._risk_summary(all_anomalies),
        }

    def _check_duplicate(self, iznos, partner_oib, datum):
        if not partner_oib or iznos == 0:
            return None
        for h in self._history[-200:]:
            if (h["partner_oib"] == partner_oib and
                abs(h["iznos"] - iznos) < 0.01 and h["datum"] and datum):
                try:
                    d1 = datetime.fromisoformat(h["datum"][:10])
                    d2 = datetime.fromisoformat(datum[:10])
                    if abs((d2 - d1).days) <= 7:
                        return Anomaly(
                            tip="DUPLIKAT", razina=RizikRazina.HIGH,
                            opis=f"Moguće duplicirano plaćanje: {iznos} EUR za OIB {partner_oib}",
                            iznos=iznos,
                            preporuka="Provjerite nije li plaćanje već izvršeno")
                except (ValueError, TypeError):
                    pass
        return None

    def _check_amount(self, iznos, konto):
        anomalies = []
        if iznos > 50_000:
            anomalies.append(Anomaly(
                tip="VISOKI_IZNOS", razina=RizikRazina.MEDIUM,
                opis=f"Iznos {iznos:.2f} EUR prelazi prag (50.000 EUR)",
                iznos=iznos, preporuka="Dodatna autorizacija za visoke iznose"))
        if iznos >= 15_000 and konto and konto.startswith("10"):
            anomalies.append(Anomaly(
                tip="AML_PRAG", razina=RizikRazina.CRITICAL,
                opis=f"Gotovinska transakcija {iznos:.2f} EUR — AML obveza",
                iznos=iznos, preporuka="Obvezna prijava AMLD"))
        if iznos >= 1000 and iznos == int(iznos) and iznos % 100 == 0:
            anomalies.append(Anomaly(
                tip="OKRUGLI_IZNOS", razina=RizikRazina.LOW,
                opis=f"Sumnjivo okrugli iznos: {iznos:.0f} EUR",
                iznos=iznos, preporuka="Okrugli iznosi mogu indicirati procjenu"))
        return anomalies

    def _check_iban_change(self, partner_oib, partner_iban):
        known = self._partner_ibans.get(partner_oib, set())
        if known and partner_iban not in known:
            return Anomaly(
                tip="IBAN_PROMJENA", razina=RizikRazina.CRITICAL,
                opis=f"Dobavljač OIB {partner_oib} koristi novi IBAN: {partner_iban}",
                preporuka="HITNO: Provjerite s dobavljačem telefonom!")
        return None

    def _check_timing(self, datum):
        if not datum or len(datum) < 13:
            return None
        try:
            dt = datetime.fromisoformat(datum)
            if dt.hour < 6 or dt.hour > 22:
                return Anomaly(
                    tip="NOCNI_UNOS", razina=RizikRazina.MEDIUM,
                    opis=f"Transakcija u {dt.hour}:{dt.minute:02d} — izvan radnog vremena",
                    preporuka="Pregledajte tko je unosio podatke noću")
            if dt.weekday() >= 5:
                return Anomaly(
                    tip="VIKEND_UNOS", razina=RizikRazina.LOW,
                    opis=f"Transakcija tijekom vikenda ({dt.strftime('%A')})",
                    preporuka="Provjerite legitimnost vikend unosa")
        except (ValueError, TypeError):
            pass
        return None

    def _benford_test(self, amounts):
        if len(amounts) < 30:
            return {"applicable": False, "reason": "Premalo podataka (min 30)"}
        expected = {1: 30.1, 2: 17.6, 3: 12.5, 4: 9.7, 5: 7.9,
                    6: 6.7, 7: 5.8, 8: 5.1, 9: 4.6}
        first_digits = []
        for a in amounts:
            if a > 0:
                s = str(abs(a)).lstrip("0").lstrip(".")
                if s and s[0].isdigit() and s[0] != "0":
                    first_digits.append(int(s[0]))
        if len(first_digits) < 30:
            return {"applicable": False, "reason": "Premalo valjanih iznosa"}
        counts = Counter(first_digits)
        total = len(first_digits)
        actual = {d: round(counts.get(d, 0) / total * 100, 1) for d in range(1, 10)}
        chi2 = sum((actual.get(d, 0) - expected[d])**2 / expected[d] for d in range(1, 10))
        suspicious = chi2 > 15.51
        return {
            "applicable": True, "expected": expected, "actual": actual,
            "chi_squared": round(chi2, 2), "suspicious": suspicious,
            "interpretation": ("UPOZORENJE: Distribucija odstupa od Benfordovog zakona"
                               if suspicious else "Distribucija unutar normalnih granica"),
        }

    def _risk_summary(self, anomalies):
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for a in anomalies:
            summary[a.razina.value] += 1
        return summary

    def get_stats(self):
        return {"module": "anomaly_detection", "total_detections": self._detections,
                "history_size": len(self._history)}


# ═══════════════════════════════════════════════
# GDPR DATA MASKING
# ═══════════════════════════════════════════════

class DataMasker:
    @staticmethod
    def mask_oib(oib: str) -> str:
        return f"********{oib[-3:]}" if len(oib) == 11 else "***"

    @staticmethod
    def mask_iban(iban: str) -> str:
        if len(iban) >= 15:
            return f"{iban[:4]}{'*' * (len(iban)-8)}{iban[-4:]}"
        return "****"

    @staticmethod
    def mask_name(name: str) -> str:
        parts = name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}. {parts[-1][0]}."
        return f"{name[0]}." if name else "***"

    @classmethod
    def mask_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        masked = dict(data)
        for key, val in masked.items():
            if not isinstance(val, str):
                continue
            k = key.lower()
            if "oib" in k:
                masked[key] = cls.mask_oib(val)
            elif "iban" in k:
                masked[key] = cls.mask_iban(val)
            elif "naziv" in k or "ime" in k or "name" in k:
                masked[key] = cls.mask_name(val)
        return masked
