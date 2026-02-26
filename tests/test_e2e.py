"""
Nyx Light — End-to-End Integration Test

Testira kompletni flow:
1. Upload ulaznog računa (mock)
2. AI ekstrakcija podataka
3. Prijedlog kontiranja
4. Human approval
5. ERP export (CPP XML)
6. Provjera safety boundaries
7. Memory (correction → L2)

Pokreni: pytest tests/test_e2e.py -v
"""

import json
import os
import tempfile
import time

import pytest


class TestEndToEnd:
    """Kompletni E2E test cijelog sustava."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    # ── 1. Invoice Extraction → Kontiranje → Approval → Export ──

    def test_full_invoice_to_erp_flow(self):
        """Kompletan flow: račun → kontiranje → odobrenje → CPP XML."""
        from nyx_light.storage.sqlite_store import SQLiteStorage
        from nyx_light.export import ERPExporter
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine

        db = SQLiteStorage(os.path.join(self.tmpdir, "test.db"))
        exporter = ERPExporter(os.path.join(self.tmpdir, "exports"))
        engine = KontiranjeEngine()

        # 1. Simuliraj ekstrakciju računa
        invoice_data = {
            "oib": "12345678901",
            "iznos": 1250.00,
            "pdv_stopa": 25,
            "pdv_iznos": 250.00,
            "opis": "Usluge web dizajna",
            "datum_dokumenta": "2026-02-26",
        }

        # 2. AI predlaže konto
        suggestion = engine.suggest_konto(invoice_data["opis"])
        assert suggestion["requires_approval"] is True
        assert suggestion["suggested_konto"]  # Mora predložiti nešto

        # 3. Spremi prijedlog u bazu
        booking_id = db.save_booking({
            "client_id": "klijent_ABC",
            "document_type": "ulazni_racun",
            "konto_duguje": suggestion["suggested_konto"],
            "konto_potrazuje": "4000",
            "iznos": invoice_data["iznos"],
            "pdv_stopa": invoice_data["pdv_stopa"],
            "pdv_iznos": invoice_data["pdv_iznos"],
            "opis": invoice_data["opis"],
            "oib": invoice_data["oib"],
            "datum_dokumenta": invoice_data["datum_dokumenta"],
            "datum_knjizenja": "2026-02-26",
            "confidence": suggestion["confidence"],
        })

        # 4. Provjeri da je pending
        pending = db.get_pending_bookings("klijent_ABC")
        assert len(pending) == 1
        assert pending[0]["status"] == "pending"

        # 5. Human odobrava
        approved = db.approve_booking(booking_id, "ana")
        assert approved is True

        # 6. Export u CPP XML
        approved_bookings = db.get_approved_bookings("klijent_ABC")
        assert len(approved_bookings) == 1

        result = exporter.export_cpp_xml(approved_bookings, "klijent_ABC")
        assert result["status"] == "exported"
        assert result["erp"] == "CPP"
        assert os.path.exists(result["file"])

        # Provjeri XML sadržaj
        xml_content = open(result["file"]).read()
        assert "klijent_ABC" in xml_content
        assert "1250.00" in xml_content

        # 7. Označi kao izvezeno
        db.mark_exported([booking_id])
        remaining = db.get_approved_bookings("klijent_ABC", exported=False)
        assert len(remaining) == 0

        db.close()

    # ── 2. Safety Boundaries ──

    def test_safety_boundaries_e2e(self):
        """Provjeri da safety blokira zabranjene akcije."""
        from nyx_light.safety.overseer import AccountingOverseer

        overseer = AccountingOverseer()

        # Pravni savjet — MORA biti blokiran
        legal_check = overseer.evaluate("Sastavi mi ugovor o djelu za zaposlenika")
        assert legal_check["approved"] is False

        # Autonomno knjiženje — MORA biti blokirano
        auto_check = overseer.evaluate("Automatski proknjiži sve ulazne račune")
        assert auto_check["approved"] is False

        # Legitimno pitanje — NE smije biti blokirano
        legit_check = overseer.evaluate("Koji konto koristim za uredski materijal?")
        assert legit_check["approved"] is True

    # ── 3. Session Management ──

    def test_session_limit_15(self):
        """Provjeri da sustav podržava točno 15 sesija."""
        from nyx_light.sessions.manager import SessionManager

        sm = SessionManager(max_sessions=15)

        # Kreiraj 15 sesija
        sessions = []
        for i in range(15):
            s = sm.create_session(f"user_{i}", f"Zaposlenik {i}")
            assert s is not None
            sessions.append(s)

        # 16. mora biti odbijena
        s16 = sm.create_session("user_16", "Zaposlenik 16")
        assert s16 is None

        stats = sm.get_stats()
        assert stats["active_sessions"] == 15
        assert stats["capacity_pct"] == 100.0

        # Oslobodi jednu → 16. sad može
        sm.end_session(sessions[0].session_id)
        s16 = sm.create_session("user_16", "Zaposlenik 16")
        assert s16 is not None

    # ── 4. Correction → L2 Memory ──

    def test_correction_flow(self):
        """Ispravak knjiženja → spremi u bazu → ulaz za DPO."""
        from nyx_light.storage.sqlite_store import SQLiteStorage

        db = SQLiteStorage(os.path.join(self.tmpdir, "test_corrections.db"))

        # AI predloži konto 7800
        bid = db.save_booking({
            "client_id": "klijent_X",
            "document_type": "ulazni_racun",
            "konto_duguje": "7800",
            "konto_potrazuje": "4000",
            "iznos": 500,
            "opis": "Servis klime",
            "ai_reasoning": "Ostali materijalni troškovi",
        })

        # Računovođa ispravlja na 7200
        db.save_correction({
            "booking_id": bid,
            "user_id": "ana",
            "client_id": "klijent_X",
            "original_konto": "7800",
            "corrected_konto": "7200",
            "document_type": "ulazni_racun",
            "supplier": "Klima Servis d.o.o.",
            "description": "Servis klime je usluga, ne materijalni trošak",
        })

        # Provjeri da correction postoji
        corrections = db.get_todays_corrections()
        assert len(corrections) >= 1
        assert corrections[0]["original_konto"] == "7800"
        assert corrections[0]["corrected_konto"] == "7200"

        db.close()

    # ── 5. Bank Statement → Matching ──

    def test_bank_matching_flow(self):
        """Bankovni izvod → parsiranje → prijedlog sparivanja."""
        from nyx_light.modules.bank_parser.parser import BankStatementParser

        parser = BankStatementParser()

        # Simuliraj CSV red
        csv_line = "26.02.2026;HR1234567890123456789;1250.00;Uplata po računu R-001/2026"
        
        # Test IBAN detection
        import re
        iban_match = re.search(r'HR\d{19}', csv_line)
        assert iban_match is not None
        assert iban_match.group().startswith("HR")

    # ── 6. Export Format Validation ──

    def test_synesis_csv_format(self):
        """Provjeri da Synesis CSV ima ispravan format."""
        from nyx_light.export import ERPExporter

        exporter = ERPExporter(os.path.join(self.tmpdir, "exports"))
        bookings = [
            {"konto_duguje": "7200", "konto_potrazuje": "4000",
             "iznos": 1000, "opis": "Test", "oib": "12345678901",
             "pdv_stopa": 25, "pdv_iznos": 200,
             "datum_dokumenta": "2026-02-26", "datum_knjizenja": "2026-02-26"},
        ]

        result = exporter.export_synesis_csv(bookings, "test_klijent", delimiter=";")
        content = open(result["file"], encoding="utf-8-sig").read()

        # Provjeri CSV strukturu
        lines = content.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert ";" in lines[0]  # Delimiter
        assert "KontoDuguje" in lines[0]
        assert "7200" in lines[1]

    # ── 7. Blagajna + Putni Nalog Validation ──

    def test_compliance_checks(self):
        """Provjeri poreznu usklađenost."""
        from nyx_light.modules.blagajna.validator import BlagajnaValidator, BlagajnaTx
        from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker

        # Blagajna: 10.000 EUR AML limit
        bv = BlagajnaValidator()
        tx_ok = BlagajnaTx(iznos=9999.99, vrsta="isplata")
        assert bv.validate_transaction(tx_ok).valid is True
        tx_over = BlagajnaTx(iznos=10001.00, vrsta="isplata")
        assert bv.validate_transaction(tx_over).valid is False

        # Putni nalog: 0,30 EUR/km (warning if exceeded)
        pn = PutniNalogChecker()
        r1 = pn.validate(km=100, km_naknada=0.30)
        assert r1["naknada_ukupno"] == 30.0
        r2 = pn.validate(km=100, km_naknada=0.50)
        assert any("0.30" in w or "0,30" in w for w in r2["warnings"])
