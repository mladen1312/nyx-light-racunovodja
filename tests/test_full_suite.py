"""Tests za ERP Export (CPP + Synesis)."""

import json
import os
import tempfile
import pytest
from nyx_light.export import ERPExporter


class TestERPExporter:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.exporter = ERPExporter(export_dir=self.tmpdir)

    def _sample_bookings(self):
        return [
            {
                "konto_duguje": "7200",
                "konto_potrazuje": "4000",
                "iznos": 1250.00,
                "opis": "Usluga web dizajna",
                "oib": "12345678901",
                "pdv_stopa": 25,
                "pdv_iznos": 250.00,
                "datum_dokumenta": "2026-02-26",
                "datum_knjizenja": "2026-02-26",
            },
            {
                "konto_duguje": "7000",
                "konto_potrazuje": "4000",
                "iznos": 500.00,
                "opis": "Uredski materijal",
                "oib": "98765432109",
                "pdv_stopa": 25,
                "pdv_iznos": 100.00,
                "datum_dokumenta": "2026-02-25",
                "datum_knjizenja": "2026-02-26",
            },
        ]

    def test_export_cpp_xml(self):
        result = self.exporter.export_cpp_xml(self._sample_bookings(), "klijent_ABC")
        assert result["status"] == "exported"
        assert result["erp"] == "CPP"
        assert result["format"] == "XML"
        assert result["records"] == 2
        assert os.path.exists(result["file"])

        # Provjeri XML sadržaj
        content = open(result["file"]).read()
        assert "<KnjizenjaImport>" in content
        assert "<KontoDuguje>7200</KontoDuguje>" in content
        assert "<Iznos>1250.00</Iznos>" in content
        assert "NyxLight" in content

    def test_export_synesis_csv(self):
        result = self.exporter.export_synesis_csv(self._sample_bookings(), "klijent_XYZ")
        assert result["status"] == "exported"
        assert result["erp"] == "Synesis"
        assert result["format"] == "CSV"
        assert os.path.exists(result["file"])

        # Provjeri CSV sadržaj
        content = open(result["file"]).read()
        assert "KontoDuguje" in content  # header
        assert "7200" in content
        assert "1250.00" in content

    def test_export_synesis_json(self):
        result = self.exporter.export_synesis_json(self._sample_bookings(), "klijent_XYZ")
        assert result["status"] == "exported"
        assert result["format"] == "JSON"
        assert os.path.exists(result["file"])

        data = json.load(open(result["file"]))
        assert data["meta"]["record_count"] == 2
        assert data["bookings"][0]["konto_duguje"] == "7200"

    def test_universal_export(self):
        # CPP
        r1 = self.exporter.export(self._sample_bookings(), "test", erp="CPP")
        assert r1["erp"] == "CPP"

        # Synesis CSV
        r2 = self.exporter.export(self._sample_bookings(), "test", erp="Synesis", fmt="CSV")
        assert r2["erp"] == "Synesis"
        assert r2["format"] == "CSV"

        # Synesis JSON
        r3 = self.exporter.export(self._sample_bookings(), "test", erp="Synesis", fmt="JSON")
        assert r3["format"] == "JSON"

    def test_export_stats(self):
        self.exporter.export_cpp_xml(self._sample_bookings(), "test")
        self.exporter.export_synesis_csv(self._sample_bookings(), "test")
        stats = self.exporter.get_stats()
        assert stats["total_exports"] == 2
"""Tests za Session Manager."""

from nyx_light.sessions.manager import SessionManager


class TestSessionManager:
    def setup_method(self):
        self.sm = SessionManager(max_sessions=3)

    def test_create_session(self):
        s = self.sm.create_session("user1", "Ana")
        assert s is not None
        assert s.user_name == "Ana"

    def test_session_limit(self):
        self.sm.create_session("user1", "Ana")
        self.sm.create_session("user2", "Marko")
        self.sm.create_session("user3", "Ivana")
        # 4th should fail
        s4 = self.sm.create_session("user4", "Petar")
        assert s4 is None

    def test_existing_session_reuse(self):
        s1 = self.sm.create_session("user1", "Ana")
        s2 = self.sm.create_session("user1", "Ana")
        assert s1.session_id == s2.session_id

    def test_end_session(self):
        s = self.sm.create_session("user1", "Ana")
        self.sm.end_session(s.session_id)
        assert self.sm.get_session(s.session_id) is None

    def test_active_sessions(self):
        self.sm.create_session("user1", "Ana")
        self.sm.create_session("user2", "Marko")
        active = self.sm.get_active_sessions()
        assert len(active) == 2

    def test_record_message(self):
        s = self.sm.create_session("user1", "Ana")
        self.sm.record_message(s.session_id)
        self.sm.record_message(s.session_id)
        assert s.message_count == 2

    def test_stats(self):
        self.sm.create_session("user1", "Ana")
        stats = self.sm.get_stats()
        assert stats["active_sessions"] == 1
        assert stats["max_sessions"] == 3
"""Tests za SQLite Storage."""

import os
import tempfile
from nyx_light.storage.sqlite_store import SQLiteStorage


class TestSQLiteStorage:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = SQLiteStorage(os.path.join(self.tmpdir, "test.db"))

    def teardown_method(self):
        self.db.close()

    def test_save_and_get_booking(self):
        booking_id = self.db.save_booking({
            "client_id": "client_A",
            "document_type": "ulazni_racun",
            "konto_duguje": "7200",
            "konto_potrazuje": "4000",
            "iznos": 1000.0,
            "opis": "Test",
        })
        pending = self.db.get_pending_bookings("client_A")
        assert len(pending) == 1
        assert pending[0]["iznos"] == 1000.0

    def test_approve_booking(self):
        bid = self.db.save_booking({
            "client_id": "client_A",
            "document_type": "ulazni_racun",
            "iznos": 500,
        })
        result = self.db.approve_booking(bid, "user_ana")
        assert result is True

        approved = self.db.get_approved_bookings("client_A")
        assert len(approved) == 1
        assert approved[0]["approved_by"] == "user_ana"

    def test_reject_booking(self):
        bid = self.db.save_booking({
            "client_id": "client_A",
            "document_type": "ulazni_racun",
            "iznos": 500,
        })
        self.db.reject_booking(bid, "user_marko", "Krivi konto")
        pending = self.db.get_pending_bookings("client_A")
        assert len(pending) == 0

    def test_save_correction(self):
        self.db.save_correction({
            "user_id": "user_ana",
            "client_id": "client_A",
            "original_konto": "7800",
            "corrected_konto": "7200",
            "document_type": "ulazni_racun",
            "supplier": "Dobavljač XYZ",
        })
        corrections = self.db.get_todays_corrections()
        assert len(corrections) >= 1

    def test_stats(self):
        self.db.save_booking({"client_id": "A", "document_type": "test", "iznos": 100})
        stats = self.db.get_stats()
        assert stats["total_bookings"] >= 1
"""Tests za System Prompts."""

from nyx_light.prompts.accounting import (
    get_chat_prompt,
    get_tax_prompt,
    KONTIRANJE_PROMPT,
    BLAGAJNA_PROMPT,
    PUTNI_NALOG_PROMPT,
)


class TestPrompts:
    def test_chat_prompt_contains_rules(self):
        prompt = get_chat_prompt("klijent_A", "Ana")
        assert "hrvatski" in prompt.lower() or "hrvatskom" in prompt.lower()
        assert "zakon" in prompt.lower()
        assert "odobr" in prompt.lower()
        assert "Ana" in prompt
        assert "klijent_A" in prompt

    def test_tax_prompt_date(self):
        prompt = get_tax_prompt("15.03.2025.")
        assert "15.03.2025." in prompt

    def test_kontiranje_prompt(self):
        assert "konto" in KONTIRANJE_PROMPT.lower()
        assert "duguje" in KONTIRANJE_PROMPT.lower()

    def test_blagajna_prompt(self):
        assert "10.000" in BLAGAJNA_PROMPT

    def test_putni_nalog_prompt(self):
        assert "0,30" in PUTNI_NALOG_PROMPT
        assert "reprezentacija" in PUTNI_NALOG_PROMPT.lower()
"""Tests za Kontiranje Engine."""

from nyx_light.modules.kontiranje.engine import KontiranjeEngine


class TestKontiranjeEngine:
    def setup_method(self):
        self.engine = KontiranjeEngine()

    def test_suggest_material(self):
        result = self.engine.suggest_konto("Nabava materijala za proizvodnju")
        assert result["suggested_konto"] == "7000"
        assert result["requires_approval"] is True

    def test_suggest_services(self):
        result = self.engine.suggest_konto("Usluga servisa klima uređaja")
        assert result["suggested_konto"] == "7200"

    def test_suggest_with_memory_hint(self):
        hint = {"hint": "konto 7500", "confidence": 0.95}
        result = self.engine.suggest_konto("Plaće", memory_hint=hint)
        assert "7500" in result["suggested_konto"]
        assert result["confidence"] == 0.95

    def test_amortizacijske_stope(self):
        assert KontiranjeEngine.AMORTIZACIJSKE_STOPE["računalna_oprema"] == 50.0
        assert KontiranjeEngine.AMORTIZACIJSKE_STOPE["vozila"] == 20.0
"""Tests za Blagajna i Putni Nalozi."""

from nyx_light.modules.blagajna.validator import BlagajnaValidator
from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker


class TestBlagajna:
    def setup_method(self):
        self.validator = BlagajnaValidator()

    def test_valid_amount(self):
        result = self.validator.validate(5000.0)
        assert result["valid"] is True

    def test_exceeds_limit(self):
        result = self.validator.validate(15000.0)
        assert result["valid"] is False
        assert "10.000" in result["warnings"][0] or "10000" in result["warnings"][0]


class TestPutniNalozi:
    def setup_method(self):
        self.checker = PutniNalogChecker()

    def test_valid_km_rate(self):
        result = self.checker.validate(km=200, km_naknada=0.30)
        assert result["naknada_ukupno"] == 60.0

    def test_exceeds_km_rate(self):
        result = self.checker.validate(km=200, km_naknada=0.50)
        assert any("0.30" in w or "0,30" in w for w in result["warnings"])

    def test_reprezentacija_warning(self):
        result = self.checker.validate(km=100, reprezentacija=500.0)
        assert any("reprezentacij" in w.lower() for w in result["warnings"])
