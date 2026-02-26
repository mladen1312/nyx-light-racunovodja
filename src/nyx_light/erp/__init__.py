"""
Nyx Light — Dvosmjerna ERP Integracija (CPP + Synesis)

Ovaj modul omogućuje:
1. EXPORT (push) — slanje knjiženja u ERP (postojeće)
2. IMPORT (pull) — čitanje podataka iz ERP-a (novo)
3. AUTONOMNI MOD — AI samostalno knjiži bez čekanja odobrenja

VAŽNO — AUTONOMNI MOD:
  - Mora se EKSPLICITNO uključiti po klijentu (default: OFF)
  - Samo za knjiženja s confidence >= 0.95
  - Svako autonomno knjiženje se logira u audit trail
  - Računovođa može u svakom trenutku isključiti
  - OVERSEER granice i dalje vrijede (AML, limiti itd.)

Metode komunikacije s ERP-om:
  - File-based: Nyx piše/čita XML/CSV iz watch foldera
  - API-based: REST/SOAP pozivi na lokalni CPP/Synesis server
  - ODBC/Database: Direktan pristup SQL bazi ERP-a (samo čitanje)
"""

import csv
import json
import logging
import os
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("nyx_light.erp.connector")

# ═══════════════════════════════════════════════════
# CONNECTOR CONFIG
# ═══════════════════════════════════════════════════

class ERPConnectionConfig:
    """Konfiguracija konekcije za jedan ERP sustav."""

    def __init__(
        self,
        erp_type: str = "CPP",           # CPP, Synesis
        method: str = "file",             # file, api, odbc
        # File-based
        export_dir: str = "",             # Folder za izvoz (Nyx → ERP)
        import_dir: str = "",             # Folder za uvoz (ERP → Nyx)
        watch_dir: str = "",              # Watch folder za nove dokumente
        # API-based
        api_url: str = "",                # http://localhost:PORT/api
        api_key: str = "",
        api_user: str = "",
        api_pass: str = "",
        # ODBC/Database (read-only)
        db_type: str = "",                # sqlite, mssql, mysql, postgresql
        db_connection_string: str = "",
        # Autonomni mod
        auto_book: bool = False,          # EKSPLICITNO uključiti
        auto_book_min_confidence: float = 0.95,
        auto_book_max_amount: float = 50_000.0,  # Max iznos za autonomno
    ):
        self.erp_type = erp_type
        self.method = method
        self.export_dir = export_dir
        self.import_dir = import_dir
        self.watch_dir = watch_dir
        self.api_url = api_url
        self.api_key = api_key
        self.api_user = api_user
        self.api_pass = api_pass
        self.db_type = db_type
        self.db_connection_string = db_connection_string
        self.auto_book = auto_book
        self.auto_book_min_confidence = auto_book_min_confidence
        self.auto_book_max_amount = auto_book_max_amount


# ═══════════════════════════════════════════════════
# BASE CONNECTOR
# ═══════════════════════════════════════════════════

class ERPConnector:
    """Bazni konektor za ERP sustave."""

    def __init__(self, config: ERPConnectionConfig):
        self.config = config
        self._audit_log: List[Dict] = []

    # ── PUSH (Export → ERP) ──

    def push_bookings(self, bookings: List[Dict], client_id: str) -> Dict[str, Any]:
        """Pošalji knjiženja u ERP sustav."""
        method = self.config.method

        if method == "file":
            return self._push_via_file(bookings, client_id)
        elif method == "api":
            return self._push_via_api(bookings, client_id)
        elif method == "odbc":
            return {"error": "ODBC push nije podržan — koristite file ili api metodu"}
        else:
            return {"error": f"Nepoznata metoda: {method}"}

    def push_auto(self, bookings: List[Dict], client_id: str,
                   confidence: float) -> Dict[str, Any]:
        """Autonomno knjiženje — BUDUĆA OPCIJA, ISKLJUČENA PO DEFAULT-u.

        Ovo se NE SMIJE aktivirati dok sustav nije 100% testiran i
        dok računovođa eksplicitno ne odobri aktivaciju za specifičnog klijenta.

        Kad je uključen:
        - Samo za ponavljajuća, rutinska knjiženja (npr. isti dobavljač svaki mjesec)
        - Confidence mora biti ≥ 95% (konfigurirano)
        - Iznos mora biti ≤ max_amount (default 50k EUR)
        - OVERSEER sigurnosne granice i dalje vrijede
        - Svako autonomno knjiženje ide u audit log
        - Računovođa može isključiti u SVAKOM trenutku
        - Računovođa dobiva dnevni email s listom autonomnih knjiženja
        """
        if not self.config.auto_book:
            return {
                "status": "blocked",
                "reason": "Autonomno knjiženje nije uključeno za ovog klijenta",
            }

        if confidence < self.config.auto_book_min_confidence:
            return {
                "status": "blocked",
                "reason": f"Confidence {confidence:.2f} < minimum {self.config.auto_book_min_confidence}",
            }

        total = sum(b.get("iznos", 0) for b in bookings)
        if total > self.config.auto_book_max_amount:
            return {
                "status": "blocked",
                "reason": f"Ukupni iznos {total:.2f} > max {self.config.auto_book_max_amount}",
            }

        # Autonomno knjiženje
        result = self.push_bookings(bookings, client_id)
        result["auto_booked"] = True
        result["confidence"] = confidence

        # Audit log
        self._audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "action": "auto_book",
            "client_id": client_id,
            "records": len(bookings),
            "total_amount": total,
            "confidence": confidence,
        })

        logger.warning(
            "🤖 AUTONOMNO KNJIŽENJE: klijent=%s, stavki=%d, iznos=%.2f, confidence=%.2f",
            client_id, len(bookings), total, confidence,
        )
        return result

    # ── PULL (Import ← ERP) ──

    def pull_kontni_plan(self) -> List[Dict]:
        """Dohvati kontni plan iz ERP-a."""
        method = self.config.method
        if method == "file":
            return self._pull_file_kontni_plan()
        elif method == "api":
            return self._pull_api_kontni_plan()
        elif method == "odbc":
            return self._pull_odbc_kontni_plan()
        return []

    def pull_otvorene_stavke(self, konto: str = "", partner_oib: str = "") -> List[Dict]:
        """Dohvati otvorene (nepodmirene) stavke iz ERP-a."""
        method = self.config.method
        if method == "file":
            return self._pull_file_otvorene(konto, partner_oib)
        elif method == "api":
            return self._pull_api_otvorene(konto, partner_oib)
        elif method == "odbc":
            return self._pull_odbc_otvorene(konto, partner_oib)
        return []

    def pull_saldo_konta(self, konto: str) -> Dict[str, Any]:
        """Dohvati saldo konta iz ERP-a."""
        if self.config.method == "odbc":
            return self._pull_odbc_saldo(konto)
        elif self.config.method == "api":
            return self._pull_api_saldo(konto)
        return {"konto": konto, "saldo": 0, "source": "unavailable"}

    def pull_bruto_bilanca(self, period: str = "") -> List[Dict]:
        """Dohvati bruto bilancu iz ERP-a."""
        if self.config.method == "odbc":
            return self._pull_odbc_bruto_bilanca(period)
        elif self.config.method == "file":
            return self._pull_file_bruto_bilanca(period)
        return []

    def pull_partner_kartice(self, oib: str) -> List[Dict]:
        """Dohvati karticu partnera (sve transakcije) iz ERP-a."""
        if self.config.method == "odbc":
            return self._pull_odbc_partner_kartica(oib)
        return []

    # ── WATCH (Monitor foldera za nove dokumente) ──

    def scan_watch_folder(self) -> List[Dict]:
        """Skeniraj watch folder za nove dokumente (PDF, XML, CSV)."""
        watch = Path(self.config.watch_dir) if self.config.watch_dir else None
        if not watch or not watch.exists():
            return []

        found = []
        for ext in ("*.pdf", "*.xml", "*.csv", "*.xlsx"):
            for f in watch.glob(ext):
                found.append({
                    "path": str(f),
                    "name": f.name,
                    "ext": f.suffix.lower(),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
        return sorted(found, key=lambda x: x["modified"], reverse=True)

    # ══════════════════════════════════════════
    # FILE-BASED IMPLEMENTACIJE
    # ══════════════════════════════════════════

    def _push_via_file(self, bookings: List[Dict], client_id: str) -> Dict:
        export_dir = Path(self.config.export_dir or f"data/exports/{self.config.erp_type.lower()}")
        export_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())

        if self.config.erp_type.upper() == "CPP":
            return self._write_cpp_xml(bookings, client_id, export_dir, ts)
        else:
            return self._write_synesis_csv(bookings, client_id, export_dir, ts)

    def _write_cpp_xml(self, bookings, client_id, export_dir, ts) -> Dict:
        root = ET.Element("KnjizenjaImport")
        header = ET.SubElement(root, "Zaglavlje")
        ET.SubElement(header, "Klijent").text = client_id
        ET.SubElement(header, "Datum").text = datetime.now().strftime("%Y-%m-%d")
        ET.SubElement(header, "Generator").text = "NyxLight-v2.0"

        stavke = ET.SubElement(root, "Stavke")
        for i, b in enumerate(bookings, 1):
            s = ET.SubElement(stavke, "Stavka")
            ET.SubElement(s, "Rb").text = str(i)
            ET.SubElement(s, "KontoDuguje").text = str(b.get("konto_duguje", ""))
            ET.SubElement(s, "KontoPotrazuje").text = str(b.get("konto_potrazuje", ""))
            ET.SubElement(s, "Iznos").text = f"{b.get('iznos', 0):.2f}"
            ET.SubElement(s, "Opis").text = str(b.get("opis", ""))
            ET.SubElement(s, "Datum").text = str(b.get("datum_dokumenta", ""))
            ET.SubElement(s, "OIB").text = str(b.get("oib", ""))

        filename = f"nyx_cpp_{client_id}_{ts}.xml"
        filepath = export_dir / filename
        tree = ET.ElementTree(root)
        tree.write(str(filepath), encoding="unicode", xml_declaration=True)

        return {"status": "exported", "erp": "CPP", "file": str(filepath),
                "records": len(bookings)}

    def _write_synesis_csv(self, bookings, client_id, export_dir, ts) -> Dict:
        filename = f"nyx_synesis_{client_id}_{ts}.csv"
        filepath = export_dir / filename
        fields = ["Rb", "KontoDuguje", "KontoPotrazuje", "Iznos", "Opis", "Datum", "OIB"]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
            w.writeheader()
            for i, b in enumerate(bookings, 1):
                w.writerow({
                    "Rb": i, "KontoDuguje": b.get("konto_duguje", ""),
                    "KontoPotrazuje": b.get("konto_potrazuje", ""),
                    "Iznos": f"{b.get('iznos', 0):.2f}",
                    "Opis": b.get("opis", ""), "Datum": b.get("datum_dokumenta", ""),
                    "OIB": b.get("oib", ""),
                })

        return {"status": "exported", "erp": "Synesis", "file": str(filepath),
                "records": len(bookings)}

    def _pull_file_kontni_plan(self) -> List[Dict]:
        import_dir = Path(self.config.import_dir) if self.config.import_dir else None
        if not import_dir:
            return []
        for name in ("kontni_plan.csv", "konta.csv", "chart_of_accounts.csv"):
            fp = import_dir / name
            if fp.exists():
                return self._parse_csv(fp)
        return []

    def _pull_file_otvorene(self, konto="", oib="") -> List[Dict]:
        import_dir = Path(self.config.import_dir) if self.config.import_dir else None
        if not import_dir:
            return []
        for name in ("otvorene_stavke.csv", "open_items.csv"):
            fp = import_dir / name
            if fp.exists():
                items = self._parse_csv(fp)
                if konto:
                    items = [i for i in items if i.get("konto", "") == konto]
                if oib:
                    items = [i for i in items if i.get("oib", "") == oib]
                return items
        return []

    def _pull_file_bruto_bilanca(self, period="") -> List[Dict]:
        import_dir = Path(self.config.import_dir) if self.config.import_dir else None
        if not import_dir:
            return []
        for name in ("bruto_bilanca.csv", "trial_balance.csv"):
            fp = import_dir / name
            if fp.exists():
                return self._parse_csv(fp)
        return []

    def _parse_csv(self, filepath: Path) -> List[Dict]:
        result = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            for delim in (";", ",", "\t"):
                f.seek(0)
                reader = csv.DictReader(f, delimiter=delim)
                rows = list(reader)
                if rows and len(rows[0]) > 1:
                    return rows
        return result

    # ══════════════════════════════════════════
    # API-BASED IMPLEMENTACIJE (stub za lokalni server)
    # ══════════════════════════════════════════

    def _push_via_api(self, bookings: List[Dict], client_id: str) -> Dict:
        """Push putem REST API-ja."""
        try:
            import httpx
        except ImportError:
            return {"error": "httpx nije instaliran — pip install httpx"}

        url = f"{self.config.api_url}/import/bookings"
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        payload = {
            "client_id": client_id,
            "generator": "NyxLight-v2.0",
            "bookings": bookings,
        }

        try:
            with httpx.Client(timeout=30) as client:
                if self.config.api_user:
                    resp = client.post(url, json=payload, headers=headers,
                                       auth=(self.config.api_user, self.config.api_pass))
                else:
                    resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return {"status": "exported", "erp": self.config.erp_type,
                        "method": "api", "response": resp.json(), "records": len(bookings)}
        except Exception as e:
            logger.error("API push error: %s", e)
            return {"status": "error", "error": str(e)}

    def _pull_api_kontni_plan(self) -> List[Dict]:
        return self._api_get("/export/kontni-plan")

    def _pull_api_otvorene(self, konto="", oib="") -> List[Dict]:
        params = {}
        if konto: params["konto"] = konto
        if oib: params["oib"] = oib
        return self._api_get("/export/otvorene-stavke", params)

    def _pull_api_saldo(self, konto: str) -> Dict:
        items = self._api_get(f"/export/saldo/{konto}")
        if items and isinstance(items, list) and len(items) > 0:
            return items[0]
        return {"konto": konto, "saldo": 0}

    def _api_get(self, path: str, params: Dict = None) -> List[Dict]:
        try:
            import httpx
        except ImportError:
            return []

        url = f"{self.config.api_url}{path}"
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=headers, params=params or {})
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, list) else data.get("items", [data])
        except Exception as e:
            logger.error("API GET %s error: %s", path, e)
            return []

    # ══════════════════════════════════════════
    # ODBC/DATABASE (Read-Only)
    # ══════════════════════════════════════════

    def _get_db_conn(self):
        """Otvori konekciju na bazu ERP-a (samo čitanje)."""
        db_type = self.config.db_type.lower()
        conn_str = self.config.db_connection_string

        if db_type == "sqlite":
            conn = sqlite3.connect(conn_str)
            conn.row_factory = sqlite3.Row
            return conn
        elif db_type == "mssql":
            try:
                import pyodbc
                return pyodbc.connect(conn_str)
            except ImportError:
                logger.error("pyodbc nije instaliran za MSSQL")
                return None
        elif db_type in ("mysql", "postgresql"):
            # Placeholder za mysql/postgres — instalirati odgovarajući driver
            logger.error("DB tip %s: instalirajte odgovarajući Python driver", db_type)
            return None
        return None

    def _pull_odbc_kontni_plan(self) -> List[Dict]:
        conn = self._get_db_conn()
        if not conn:
            return []
        try:
            # CPP i Synesis tipično imaju tablicu KontniPlan ili Konta
            for table in ("KontniPlan", "Konta", "ChartOfAccounts", "kontni_plan"):
                try:
                    cur = conn.execute(f"SELECT * FROM {table}")
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
                except Exception:
                    continue
            return []
        finally:
            conn.close()

    def _pull_odbc_otvorene(self, konto="", oib="") -> List[Dict]:
        conn = self._get_db_conn()
        if not conn:
            return []
        try:
            sql = "SELECT * FROM OtvoreneStavke WHERE 1=1"
            params = []
            if konto:
                sql += " AND Konto = ?"
                params.append(konto)
            if oib:
                sql += " AND OIB = ?"
                params.append(oib)
            cur = conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error("ODBC pull otvorene: %s", e)
            return []
        finally:
            conn.close()

    def _pull_odbc_saldo(self, konto: str) -> Dict:
        conn = self._get_db_conn()
        if not conn:
            return {"konto": konto, "saldo": 0}
        try:
            for sql in [
                "SELECT SUM(Duguje)-SUM(Potrazuje) as Saldo FROM Knjizenja WHERE Konto=?",
                "SELECT Saldo FROM SaldaKonta WHERE Konto=?",
            ]:
                try:
                    cur = conn.execute(sql, (konto,))
                    row = cur.fetchone()
                    if row:
                        return {"konto": konto, "saldo": float(row[0] or 0), "source": "odbc"}
                except Exception:
                    continue
            return {"konto": konto, "saldo": 0}
        finally:
            conn.close()

    def _pull_odbc_bruto_bilanca(self, period="") -> List[Dict]:
        conn = self._get_db_conn()
        if not conn:
            return []
        try:
            sql = """
                SELECT Konto, SUM(Duguje) as Duguje, SUM(Potrazuje) as Potrazuje,
                       SUM(Duguje)-SUM(Potrazuje) as Saldo
                FROM Knjizenja
                WHERE 1=1
            """
            params = []
            if period:
                sql += " AND strftime('%Y-%m', DatumKnjizenja) = ?"
                params.append(period)
            sql += " GROUP BY Konto ORDER BY Konto"
            cur = conn.execute(sql, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            logger.error("ODBC bruto bilanca: %s", e)
            return []
        finally:
            conn.close()

    def _pull_odbc_partner_kartica(self, oib: str) -> List[Dict]:
        conn = self._get_db_conn()
        if not conn:
            return []
        try:
            sql = "SELECT * FROM Knjizenja WHERE OIB=? ORDER BY DatumKnjizenja"
            cur = conn.execute(sql, (oib,))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            return []
        finally:
            conn.close()

    # ══════════════════════════════════════════
    # AUDIT & STATUS
    # ══════════════════════════════════════════

    def get_audit_log(self) -> List[Dict]:
        return self._audit_log

    def test_connection(self) -> Dict[str, Any]:
        """Testiraj konekciju na ERP."""
        method = self.config.method
        result = {"erp": self.config.erp_type, "method": method}

        if method == "file":
            exp = Path(self.config.export_dir) if self.config.export_dir else None
            imp = Path(self.config.import_dir) if self.config.import_dir else None
            result["export_dir_exists"] = exp.exists() if exp else False
            result["import_dir_exists"] = imp.exists() if imp else False
            result["status"] = "ok" if (exp and exp.exists()) else "check_dirs"

        elif method == "api":
            try:
                import httpx
                with httpx.Client(timeout=5) as c:
                    resp = c.get(f"{self.config.api_url}/health")
                    result["status"] = "ok" if resp.status_code == 200 else f"http_{resp.status_code}"
            except Exception as e:
                result["status"] = f"error: {e}"

        elif method == "odbc":
            conn = self._get_db_conn()
            if conn:
                result["status"] = "ok"
                conn.close()
            else:
                result["status"] = "connection_failed"

        result["auto_book"] = self.config.auto_book
        return result

    def get_stats(self):
        return {
            "erp": self.config.erp_type,
            "method": self.config.method,
            "auto_book": self.config.auto_book,
            "audit_log_entries": len(self._audit_log),
        }


# ═══════════════════════════════════════════════════
# CONVENIENCE: FACTORY
# ═══════════════════════════════════════════════════

def create_cpp_connector(
    method: str = "file",
    export_dir: str = "data/exports/cpp",
    import_dir: str = "data/imports/cpp",
    auto_book: bool = False,
    **kwargs,
) -> ERPConnector:
    """Kreiraj CPP konektor."""
    config = ERPConnectionConfig(
        erp_type="CPP", method=method,
        export_dir=export_dir, import_dir=import_dir,
        auto_book=auto_book, **kwargs,
    )
    return ERPConnector(config)


def create_synesis_connector(
    method: str = "file",
    export_dir: str = "data/exports/synesis",
    import_dir: str = "data/imports/synesis",
    auto_book: bool = False,
    **kwargs,
) -> ERPConnector:
    """Kreiraj Synesis konektor."""
    config = ERPConnectionConfig(
        erp_type="Synesis", method=method,
        export_dir=export_dir, import_dir=import_dir,
        auto_book=auto_book, **kwargs,
    )
    return ERPConnector(config)
