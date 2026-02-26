"""
Tests: Dvosmjerna ERP Integracija + Autonomno knjiženje.
Testira: file push/pull, auto-book, audit log, OVERSEER blokada.
"""
import csv
import json
import os
import tempfile
import pytest
from pathlib import Path


class TestERPConnectorConfig:
    """Konfiguracija ERP konektora."""

    def test_default_config(self):
        from nyx_light.erp import ERPConnectionConfig
        cfg = ERPConnectionConfig()
        assert cfg.erp_type == "CPP"
        assert cfg.method == "file"
        assert cfg.auto_book is False
        assert cfg.auto_book_min_confidence == 0.95

    def test_custom_config(self):
        from nyx_light.erp import ERPConnectionConfig
        cfg = ERPConnectionConfig(
            erp_type="Synesis", method="api",
            api_url="http://localhost:9090",
            auto_book=True, auto_book_max_amount=100_000,
        )
        assert cfg.erp_type == "Synesis"
        assert cfg.auto_book is True
        assert cfg.auto_book_max_amount == 100_000


class TestERPFilePush:
    """Export (push) knjiženja u ERP putem file metode."""

    def setup_method(self):
        from nyx_light.erp import ERPConnector, ERPConnectionConfig
        self.tmpdir = tempfile.mkdtemp()
        self.cfg_cpp = ERPConnectionConfig(
            erp_type="CPP", method="file",
            export_dir=os.path.join(self.tmpdir, "cpp_out"),
        )
        self.cfg_syn = ERPConnectionConfig(
            erp_type="Synesis", method="file",
            export_dir=os.path.join(self.tmpdir, "syn_out"),
        )
        self.conn_cpp = ERPConnector(self.cfg_cpp)
        self.conn_syn = ERPConnector(self.cfg_syn)

    def _bookings(self):
        return [
            {"konto_duguje": "4000", "konto_potrazuje": "1200",
             "iznos": 1250.00, "opis": "Račun dobavljač A",
             "datum_dokumenta": "2026-02-26", "oib": "12345678901"},
            {"konto_duguje": "1400", "konto_potrazuje": "4000",
             "iznos": 250.00, "opis": "Pretporez 25%",
             "datum_dokumenta": "2026-02-26", "oib": "12345678901"},
        ]

    def test_push_cpp_xml(self):
        r = self.conn_cpp.push_bookings(self._bookings(), "K001")
        assert r["status"] == "exported"
        assert r["erp"] == "CPP"
        assert r["records"] == 2
        assert os.path.exists(r["file"])
        # Check XML content
        content = open(r["file"]).read()
        assert "<KnjizenjaImport>" in content
        assert "4000" in content

    def test_push_synesis_csv(self):
        r = self.conn_syn.push_bookings(self._bookings(), "K002")
        assert r["status"] == "exported"
        assert r["erp"] == "Synesis"
        assert r["records"] == 2
        assert r["file"].endswith(".csv")
        # Read CSV
        with open(r["file"], encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["KontoDuguje"] == "4000"


class TestERPFilePull:
    """Import (pull) podataka iz ERP-a putem file metode."""

    def setup_method(self):
        from nyx_light.erp import ERPConnector, ERPConnectionConfig
        self.tmpdir = tempfile.mkdtemp()
        self.import_dir = os.path.join(self.tmpdir, "imports")
        os.makedirs(self.import_dir)
        self.cfg = ERPConnectionConfig(
            erp_type="CPP", method="file",
            import_dir=self.import_dir,
        )
        self.conn = ERPConnector(self.cfg)

    def _write_csv(self, filename, rows, header):
        fp = os.path.join(self.import_dir, filename)
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=header, delimiter=";")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    def test_pull_kontni_plan(self):
        self._write_csv("kontni_plan.csv", [
            {"konto": "1000", "naziv": "Žiro-račun"},
            {"konto": "1200", "naziv": "Kupci"},
            {"konto": "4000", "naziv": "Dobavljači"},
        ], ["konto", "naziv"])
        result = self.conn.pull_kontni_plan()
        assert len(result) == 3
        assert result[0]["konto"] == "1000"

    def test_pull_otvorene_stavke(self):
        self._write_csv("otvorene_stavke.csv", [
            {"konto": "1200", "oib": "111", "iznos": "5000", "opis": "R-001"},
            {"konto": "1200", "oib": "222", "iznos": "3000", "opis": "R-002"},
            {"konto": "4000", "oib": "333", "iznos": "8000", "opis": "URA-001"},
        ], ["konto", "oib", "iznos", "opis"])

        # Sve
        all_items = self.conn.pull_otvorene_stavke()
        assert len(all_items) == 3

        # Filtrirano po kontu
        kupci = self.conn.pull_otvorene_stavke(konto="1200")
        assert len(kupci) == 2

        # Filtrirano po OIB-u
        partner = self.conn.pull_otvorene_stavke(partner_oib="222")
        assert len(partner) == 1
        assert partner[0]["opis"] == "R-002"

    def test_pull_bruto_bilanca(self):
        self._write_csv("bruto_bilanca.csv", [
            {"konto": "1000", "duguje": "500000", "potrazuje": "480000", "saldo": "20000"},
            {"konto": "7200", "duguje": "0", "potrazuje": "300000", "saldo": "-300000"},
        ], ["konto", "duguje", "potrazuje", "saldo"])
        result = self.conn.pull_bruto_bilanca()
        assert len(result) == 2

    def test_pull_empty_when_no_file(self):
        assert self.conn.pull_kontni_plan() == []
        assert self.conn.pull_otvorene_stavke() == []


class TestERPAutoBook:
    """Autonomno knjiženje — AI samostalno šalje u ERP."""

    def setup_method(self):
        from nyx_light.erp import ERPConnector, ERPConnectionConfig
        self.tmpdir = tempfile.mkdtemp()
        # Auto-book UKLJUČEN
        self.cfg_auto = ERPConnectionConfig(
            erp_type="CPP", method="file",
            export_dir=os.path.join(self.tmpdir, "auto_out"),
            auto_book=True,
            auto_book_min_confidence=0.95,
            auto_book_max_amount=50_000,
        )
        # Auto-book ISKLJUČEN (default)
        self.cfg_manual = ERPConnectionConfig(
            erp_type="CPP", method="file",
            export_dir=os.path.join(self.tmpdir, "manual_out"),
            auto_book=False,
        )
        self.auto = ERPConnector(self.cfg_auto)
        self.manual = ERPConnector(self.cfg_manual)

    def _bookings(self, iznos=1000):
        return [{"konto_duguje": "4000", "konto_potrazuje": "1200",
                 "iznos": iznos, "opis": "Test", "datum_dokumenta": "2026-02-26"}]

    def test_auto_book_success(self):
        r = self.auto.push_auto(self._bookings(), "K001", confidence=0.98)
        assert r["status"] == "exported"
        assert r["auto_booked"] is True
        assert r["confidence"] == 0.98

    def test_auto_book_blocked_when_disabled(self):
        r = self.manual.push_auto(self._bookings(), "K001", confidence=0.99)
        assert r["status"] == "blocked"
        assert "nije uključeno" in r["reason"]

    def test_auto_book_blocked_low_confidence(self):
        r = self.auto.push_auto(self._bookings(), "K001", confidence=0.80)
        assert r["status"] == "blocked"
        assert "Confidence" in r["reason"]

    def test_auto_book_blocked_high_amount(self):
        r = self.auto.push_auto(self._bookings(60_000), "K001", confidence=0.99)
        assert r["status"] == "blocked"
        assert "iznos" in r["reason"]

    def test_audit_log(self):
        self.auto.push_auto(self._bookings(), "K001", confidence=0.97)
        log = self.auto.get_audit_log()
        assert len(log) == 1
        assert log[0]["action"] == "auto_book"
        assert log[0]["client_id"] == "K001"
        assert log[0]["confidence"] == 0.97


class TestERPWatchFolder:
    """Skeniranje watch foldera za nove dokumente."""

    def setup_method(self):
        from nyx_light.erp import ERPConnector, ERPConnectionConfig
        self.tmpdir = tempfile.mkdtemp()
        self.watch = os.path.join(self.tmpdir, "watch")
        os.makedirs(self.watch)
        self.cfg = ERPConnectionConfig(
            erp_type="CPP", method="file", watch_dir=self.watch,
        )
        self.conn = ERPConnector(self.cfg)

    def test_scan_empty(self):
        assert self.conn.scan_watch_folder() == []

    def test_scan_finds_files(self):
        # Create test files
        Path(self.watch, "racun_001.pdf").write_text("fake pdf")
        Path(self.watch, "izvod_01.csv").write_text("a;b;c")
        Path(self.watch, "uvoz.xml").write_text("<root/>")
        Path(self.watch, "notes.txt").write_text("ignore me")  # Not watched

        found = self.conn.scan_watch_folder()
        assert len(found) == 3  # pdf, csv, xml — not txt
        exts = {f["ext"] for f in found}
        assert exts == {".pdf", ".csv", ".xml"}


class TestERPTestConnection:
    """Test konekcije na ERP."""

    def test_file_connection(self):
        from nyx_light.erp import ERPConnector, ERPConnectionConfig
        tmpdir = tempfile.mkdtemp()
        export_dir = os.path.join(tmpdir, "exports")
        os.makedirs(export_dir)
        cfg = ERPConnectionConfig(
            erp_type="CPP", method="file", export_dir=export_dir,
        )
        conn = ERPConnector(cfg)
        r = conn.test_connection()
        assert r["status"] == "ok"
        assert r["export_dir_exists"] is True


class TestFactoryFunctions:
    """Factory funkcije za kreiranje konektora."""

    def test_create_cpp(self):
        from nyx_light.erp import create_cpp_connector
        tmpdir = tempfile.mkdtemp()
        conn = create_cpp_connector(export_dir=os.path.join(tmpdir, "e"))
        assert conn.config.erp_type == "CPP"

    def test_create_synesis(self):
        from nyx_light.erp import create_synesis_connector
        tmpdir = tempfile.mkdtemp()
        conn = create_synesis_connector(export_dir=os.path.join(tmpdir, "e"))
        assert conn.config.erp_type == "Synesis"

    def test_create_with_auto_book(self):
        from nyx_light.erp import create_cpp_connector
        tmpdir = tempfile.mkdtemp()
        conn = create_cpp_connector(
            export_dir=os.path.join(tmpdir, "e"), auto_book=True,
        )
        assert conn.config.auto_book is True


class TestERPODBCSQLite:
    """ODBC pull iz SQLite baze (simulira CPP/Synesis SQL bazu)."""

    def setup_method(self):
        import sqlite3
        from nyx_light.erp import ERPConnector, ERPConnectionConfig

        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "erp.db")

        # Kreiraj test bazu koja simulira CPP/Synesis
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE KontniPlan (
                konto TEXT PRIMARY KEY,
                naziv TEXT
            )
        """)
        conn.execute("INSERT INTO KontniPlan VALUES ('1000', 'Žiro-račun')")
        conn.execute("INSERT INTO KontniPlan VALUES ('1200', 'Kupci')")
        conn.execute("INSERT INTO KontniPlan VALUES ('4000', 'Dobavljači')")

        conn.execute("""
            CREATE TABLE OtvoreneStavke (
                id INTEGER PRIMARY KEY,
                Konto TEXT, OIB TEXT, Iznos REAL, Opis TEXT
            )
        """)
        conn.execute("INSERT INTO OtvoreneStavke VALUES (1, '1200', '111', 5000, 'R-001')")
        conn.execute("INSERT INTO OtvoreneStavke VALUES (2, '1200', '222', 3000, 'R-002')")

        conn.execute("""
            CREATE TABLE Knjizenja (
                id INTEGER PRIMARY KEY,
                Konto TEXT, OIB TEXT, Duguje REAL, Potrazuje REAL,
                DatumKnjizenja TEXT, Opis TEXT
            )
        """)
        conn.execute("INSERT INTO Knjizenja VALUES (1,'1000','',500000,480000,'2026-01-15','Uplata')")
        conn.execute("INSERT INTO Knjizenja VALUES (2,'7200','',0,300000,'2026-01-15','Prihod')")
        conn.execute("INSERT INTO Knjizenja VALUES (3,'1200','111',5000,0,'2026-01-20','R-001')")
        conn.commit()
        conn.close()

        self.cfg = ERPConnectionConfig(
            erp_type="CPP", method="odbc",
            db_type="sqlite",
            db_connection_string=self.db_path,
        )
        self.connector = ERPConnector(self.cfg)

    def test_pull_kontni_plan_odbc(self):
        result = self.connector.pull_kontni_plan()
        assert len(result) == 3
        assert result[0]["konto"] == "1000"

    def test_pull_otvorene_odbc(self):
        result = self.connector.pull_otvorene_stavke(konto="1200")
        assert len(result) == 2

    def test_pull_saldo_odbc(self):
        r = self.connector.pull_saldo_konta("1000")
        assert r["saldo"] == 20_000  # 500k - 480k
        assert r["source"] == "odbc"

    def test_pull_bruto_bilanca_odbc(self):
        result = self.connector.pull_bruto_bilanca()
        assert len(result) >= 2
        # Check konto 1000
        k1000 = [r for r in result if r["Konto"] == "1000"]
        assert len(k1000) == 1
        assert float(k1000[0]["Saldo"]) == 20_000

    def test_pull_partner_kartica_odbc(self):
        result = self.connector.pull_partner_kartice("111")
        assert len(result) == 1
        assert float(result[0]["Duguje"]) == 5000


class TestE2EAppERP:
    """E2E: ERP konektor kroz NyxLightApp."""

    def setup_method(self):
        from nyx_light.app import NyxLightApp
        from nyx_light.registry import ClientConfig
        from nyx_light.erp import ERPConnectionConfig

        self.tmpdir = tempfile.mkdtemp()
        self.app = NyxLightApp(export_dir=os.path.join(self.tmpdir, "exports"))

        self.app.register_client(ClientConfig(
            id="K001", naziv="Firma Test", oib="12345678903",
            erp_target="CPP", kategorija="mali",
        ))

        # Konfiguriraj CPP konektor
        export_dir = os.path.join(self.tmpdir, "cpp_exports")
        import_dir = os.path.join(self.tmpdir, "cpp_imports")
        os.makedirs(import_dir, exist_ok=True)

        cfg = ERPConnectionConfig(
            erp_type="CPP", method="file",
            export_dir=export_dir, import_dir=import_dir,
            auto_book=True, auto_book_min_confidence=0.95,
        )
        self.app.configure_erp("K001", cfg)

        # Write test import data
        fp = os.path.join(import_dir, "kontni_plan.csv")
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["konto", "naziv"], delimiter=";")
            w.writeheader()
            w.writerow({"konto": "1000", "naziv": "Žiro"})
            w.writerow({"konto": "4000", "naziv": "Dobavljači"})

    def test_erp_pull_kontni_plan(self):
        result = self.app.erp_pull_kontni_plan("K001")
        assert len(result) == 2

    def test_erp_auto_book_success(self):
        bookings = [{"konto_duguje": "4000", "konto_potrazuje": "1200",
                      "iznos": 1000, "opis": "Račun test", "datum_dokumenta": "2026-02-26"}]
        r = self.app.erp_push_auto("K001", bookings, confidence=0.98)
        assert r["status"] == "exported"
        assert r["auto_booked"] is True

    def test_erp_auto_book_blocked_low_confidence(self):
        bookings = [{"konto_duguje": "4000", "konto_potrazuje": "1200",
                      "iznos": 1000, "opis": "Test", "datum_dokumenta": "2026-02-26"}]
        r = self.app.erp_push_auto("K001", bookings, confidence=0.50)
        assert r["status"] == "blocked"

    def test_erp_audit_log(self):
        bookings = [{"konto_duguje": "4000", "konto_potrazuje": "1200",
                      "iznos": 500, "opis": "Test", "datum_dokumenta": "2026-02-26"}]
        self.app.erp_push_auto("K001", bookings, confidence=0.99)
        log = self.app.erp_get_audit_log("K001")
        assert len(log) == 1

    def test_system_status_has_erp(self):
        status = self.app.get_system_status()
        assert "erp_connectors" in status["modules"]
        assert "K001" in status["modules"]["erp_connectors"]

    def test_no_connector_returns_empty(self):
        assert self.app.erp_pull_kontni_plan("NONEXISTENT") == []
        assert self.app.erp_pull_saldo("NONEXISTENT", "1000")["saldo"] == 0
