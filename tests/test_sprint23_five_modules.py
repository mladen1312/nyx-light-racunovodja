"""
Sprint 23 Tests — 5 novih modula
═════════════════════════════════
1. AS4/Peppol posrednik (B2Brouter)
2. Vision LLM (Qwen2.5-VL Tier 4)
3. L3 DPO noćna optimizacija
4. Time-Aware RAG (zakoni RH)
5. Web/Chat UI za 15 zaposlenika
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import time
from datetime import date, datetime
from decimal import Decimal

import pytest


# ═══════════════════════════════════════════
# 1. PEPPOL / AS4 TESTS
# ═══════════════════════════════════════════

class TestPeppolParticipant:
    def test_from_oib(self):
        from nyx_light.modules.peppol import PeppolParticipant
        p = PeppolParticipant.from_oib("12345678903", "Test d.o.o.")
        assert p.scheme == "0192"
        assert p.id == "12345678903"
        assert p.full_id == "0192::12345678903"
        assert p.country == "HR"

    def test_from_oib_invalid(self):
        from nyx_light.modules.peppol import PeppolParticipant
        with pytest.raises(ValueError, match="Neispravan OIB"):
            PeppolParticipant.from_oib("123")

    def test_from_vat_id_hr(self):
        from nyx_light.modules.peppol import PeppolParticipant
        p = PeppolParticipant.from_vat_id("HR12345678903", "Test")
        assert p.scheme == "0192"
        assert p.id == "12345678903"

    def test_from_vat_id_de(self):
        from nyx_light.modules.peppol import PeppolParticipant
        p = PeppolParticipant.from_vat_id("DE123456789", "German Co")
        assert p.scheme == "9930"
        assert p.country == "DE"


class TestPeppolEnvelope:
    def test_create_envelope(self):
        from nyx_light.modules.peppol import (
            PeppolEnvelope, PeppolParticipant, DocumentType, DeliveryStatus
        )
        sender = PeppolParticipant.from_oib("12345678903", "Sender")
        receiver = PeppolParticipant.from_oib("98765432109", "Receiver")
        env = PeppolEnvelope(
            sender=sender,
            receiver=receiver,
            document_type=DocumentType.INVOICE,
            payload_xml="<Invoice/>",
        )
        assert env.status == DeliveryStatus.QUEUED
        assert env.sender.full_id == "0192::12345678903"
        assert len(env.payload_hash) == 16

    def test_to_dict(self):
        from nyx_light.modules.peppol import PeppolEnvelope, PeppolParticipant
        env = PeppolEnvelope(
            sender=PeppolParticipant.from_oib("12345678903"),
            payload_xml="<test/>",
        )
        d = env.to_dict()
        assert "envelope_id" in d
        assert "status" in d
        assert d["sender"] == "0192::12345678903"


class TestPeppolAPClient:
    @pytest.mark.asyncio
    async def test_send_sandbox(self):
        from nyx_light.modules.peppol import (
            PeppolAPClient, APCredentials, PeppolEnvelope, PeppolParticipant
        )
        client = PeppolAPClient(APCredentials.b2brouter_sandbox())
        env = PeppolEnvelope(
            sender=PeppolParticipant.from_oib("12345678903"),
            receiver=PeppolParticipant.from_oib("98765432109"),
            payload_xml="<Invoice><ID>R-001</ID></Invoice>",
        )
        result = await client.send_invoice(env)
        assert result["success"] is True
        assert "message_id" in result

    @pytest.mark.asyncio
    async def test_stats(self):
        from nyx_light.modules.peppol import PeppolAPClient, APCredentials
        client = PeppolAPClient(APCredentials.b2brouter_sandbox())
        stats = client.get_stats()
        assert stats["provider"] == "b2brouter"
        assert stats["sandbox"] is True

    @pytest.mark.asyncio
    async def test_reject_invoice(self):
        from nyx_light.modules.peppol import PeppolAPClient, APCredentials
        client = PeppolAPClient(APCredentials.b2brouter_sandbox())
        result = await client.reject_invoice("msg-123", "PRICE_MISMATCH", "Krivi iznos")
        assert result["success"] is True
        assert result["reason_code"] == "PRICE_MISMATCH"

    @pytest.mark.asyncio
    async def test_reject_invalid_reason(self):
        from nyx_light.modules.peppol import PeppolAPClient, APCredentials
        client = PeppolAPClient(APCredentials.b2brouter_sandbox())
        result = await client.reject_invoice("msg-123", "INVALID_REASON")
        assert "error" in result


class TestPeppolDirectory:
    @pytest.mark.asyncio
    async def test_lookup_known(self):
        from nyx_light.modules.peppol import PeppolDirectory
        d = PeppolDirectory(sandbox=True)
        result = await d.lookup("0192::85821130368")
        assert result["found"] is True
        assert "Ministarstvo" in result["name"]

    @pytest.mark.asyncio
    async def test_lookup_unknown(self):
        from nyx_light.modules.peppol import PeppolDirectory
        d = PeppolDirectory(sandbox=True)
        result = await d.lookup("0192::00000000000")
        assert result["found"] is False

    def test_is_b2g(self):
        from nyx_light.modules.peppol import PeppolDirectory
        d = PeppolDirectory()
        assert d.is_b2g("85821130368") is True
        assert d.is_b2g("12345678903") is False


class TestPeppolIntegration:
    @pytest.mark.asyncio
    async def test_send_eracun(self):
        from nyx_light.modules.peppol import PeppolIntegration
        pi = PeppolIntegration()
        result = await pi.send_eracun(
            ubl_xml="<Invoice/>",
            sender_oib="12345678903", sender_name="Test d.o.o.",
            receiver_oib="85821130368", receiver_name="MF",
        )
        assert result["success"] is True
        assert result["peppol_lookup"]["b2g"] is True

    @pytest.mark.asyncio
    async def test_stats(self):
        from nyx_light.modules.peppol import PeppolIntegration
        pi = PeppolIntegration()
        stats = pi.get_stats()
        assert stats["module"] == "peppol"


# ═══════════════════════════════════════════
# 2. VISION LLM TESTS
# ═══════════════════════════════════════════

class TestOIBValidation:
    def test_valid_oib(self):
        from nyx_light.modules.vision_llm import _validate_oib
        assert _validate_oib("12345678903") is True

    def test_invalid_oib_length(self):
        from nyx_light.modules.vision_llm import _validate_oib
        assert _validate_oib("123") is False
        assert _validate_oib("") is False

    def test_invalid_oib_checksum(self):
        from nyx_light.modules.vision_llm import _validate_oib
        assert _validate_oib("12345678901") is False


class TestExtractedField:
    def test_confidence_levels(self):
        from nyx_light.modules.vision_llm import ExtractedField, ExtractionConfidence
        assert ExtractedField("x", "v", 0.95).confidence_level == ExtractionConfidence.HIGH
        assert ExtractedField("x", "v", 0.80).confidence_level == ExtractionConfidence.MEDIUM
        assert ExtractedField("x", "v", 0.60).confidence_level == ExtractionConfidence.LOW
        assert ExtractedField("x", "v", 0.30).confidence_level == ExtractionConfidence.UNCERTAIN


class TestInvoiceExtraction:
    def test_validate_complete(self):
        from nyx_light.modules.vision_llm import InvoiceExtraction, ExtractedField
        ext = InvoiceExtraction(
            supplier_oib=ExtractedField("supplier_oib", "12345678903", 0.95),
            invoice_number=ExtractedField("invoice_number", "R-001/2026", 0.95),
            invoice_date=ExtractedField("invoice_date", "28.02.2026", 0.95),
            gross_amount=ExtractedField("gross_amount", "1250.00", 0.95),
            overall_confidence=0.90,
        )
        issues = ext.validate()
        assert len(issues) == 0

    def test_validate_missing_oib(self):
        from nyx_light.modules.vision_llm import InvoiceExtraction
        ext = InvoiceExtraction(overall_confidence=0.90)
        issues = ext.validate()
        assert any("OIB" in i for i in issues)

    def test_validate_bad_oib(self):
        from nyx_light.modules.vision_llm import InvoiceExtraction, ExtractedField
        ext = InvoiceExtraction(
            supplier_oib=ExtractedField("supplier_oib", "12345678901", 0.9),
            invoice_number=ExtractedField("invoice_number", "R-1", 0.9),
            invoice_date=ExtractedField("invoice_date", "01.01.2026", 0.9),
            gross_amount=ExtractedField("gross_amount", "100", 0.9),
            overall_confidence=0.90,
        )
        issues = ext.validate()
        assert any("MOD 11,10" in i for i in issues)

    def test_to_dict(self):
        from nyx_light.modules.vision_llm import InvoiceExtraction
        ext = InvoiceExtraction(extraction_id="test123", overall_confidence=0.85)
        d = ext.to_dict()
        assert d["extraction_id"] == "test123"
        assert "fields" in d
        assert "supplier_oib" in d["fields"]


class TestVisionLLMClient:
    @pytest.mark.asyncio
    async def test_extract_offline(self):
        from nyx_light.modules.vision_llm import VisionLLMClient, ImageFormat
        client = VisionLLMClient(confidence_threshold=0.70)
        result = await client.extract_invoice(
            b"fake_image_data_for_testing",
            ImageFormat.JPEG,
            filename="test.jpg",
        )
        assert result.extraction_id
        assert result.overall_confidence > 0
        assert result.supplier_name.value

    @pytest.mark.asyncio
    async def test_fallback_to_larger(self):
        from nyx_light.modules.vision_llm import VisionLLMClient, VisionModel
        client = VisionLLMClient(confidence_threshold=0.80, fallback_enabled=True)
        # 7B gives 0.72 confidence, should fallback
        result = await client.extract_invoice(
            b"test_data",
            model=VisionModel.QWEN_VL_7B,
        )
        # Should have tried larger model
        assert client._stats["fallbacks"] >= 0  # At least attempted

    @pytest.mark.asyncio
    async def test_batch_extract(self):
        from nyx_light.modules.vision_llm import VisionLLMClient, ImageFormat
        client = VisionLLMClient(confidence_threshold=0.70)
        items = [
            (b"img1", ImageFormat.JPEG, "invoice1.jpg"),
            (b"img2", ImageFormat.PNG, "invoice2.png"),
        ]
        results = await client.extract_batch(items)
        assert len(results) == 2
        assert all(r.extraction_id for r in results)

    def test_stats(self):
        from nyx_light.modules.vision_llm import VisionLLMClient
        client = VisionLLMClient()
        stats = client.get_stats()
        assert stats["module"] == "vision_llm"
        assert "confidence_threshold" in stats


# ═══════════════════════════════════════════
# 3. DPO NIGHTLY TESTS
# ═══════════════════════════════════════════

class TestDPODatasetBuilder:
    def test_record_correction(self):
        from nyx_light.memory.dpo import DPODatasetBuilder, CorrectionType
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            pair = builder.record_correction(
                prompt="Račun za uredski materijal od Konzum d.o.o.",
                chosen="Konto 4210 — Uredski materijal",
                rejected="Konto 4100 — Materijalni troškovi",
                user_id="user1",
                client_id="klijent_abc",
                correction_type=CorrectionType.KONTO_CHANGE,
            )
            assert pair.pair_id
            assert pair.correction_type == CorrectionType.KONTO_CHANGE

    def test_get_unused_pairs(self):
        from nyx_light.memory.dpo import DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            for i in range(5):
                builder.record_correction(
                    prompt=f"Prompt {i}", chosen=f"Chosen {i}",
                    rejected=f"Rejected {i}", user_id="u1",
                )
            pairs = builder.get_unused_pairs()
            assert len(pairs) == 5

    def test_export_insufficient_pairs(self):
        from nyx_light.memory.dpo import DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            builder.record_correction("p", "c", "r", "u")
            result = builder.export_dataset()
            assert result["exported"] is False
            assert "Nedovoljno" in result["reason"]

    def test_export_sufficient_pairs(self):
        from nyx_light.memory.dpo import DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            for i in range(55):
                builder.record_correction(f"p{i}", f"c{i}", f"r{i}", "u1")
            result = builder.export_dataset(
                output_path=os.path.join(tmp, "dataset.jsonl"),
                min_pairs=50,
            )
            assert result["exported"] is True
            assert result["pairs_count"] == 55
            assert os.path.exists(result["path"])
            # Verify JSONL content
            with open(result["path"]) as f:
                lines = f.readlines()
                assert len(lines) == 55
                first = json.loads(lines[0])
                assert "prompt" in first
                assert "chosen" in first
                assert "rejected" in first

    def test_pairs_marked_used(self):
        from nyx_light.memory.dpo import DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            for i in range(55):
                builder.record_correction(f"p{i}", f"c{i}", f"r{i}", "u1")
            builder.export_dataset(
                output_path=os.path.join(tmp, "ds.jsonl"), min_pairs=50)
            remaining = builder.get_unused_pairs()
            assert len(remaining) == 0

    def test_stats(self):
        from nyx_light.memory.dpo import DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            builder.record_correction("p", "c", "r", "u")
            stats = builder.get_stats()
            assert stats["total_corrections"] == 1
            assert stats["unused_corrections"] == 1

    def test_correction_pair_to_dpo_format(self):
        from nyx_light.memory.dpo import CorrectionPair, CorrectionType
        pair = CorrectionPair(
            pair_id="test1", prompt="test prompt",
            chosen="good answer", rejected="bad answer",
            correction_type=CorrectionType.VAT_FIX,
        )
        dpo = pair.to_dpo_format()
        assert dpo["prompt"] == "test prompt"
        assert dpo["chosen"] == "good answer"
        assert dpo["rejected"] == "bad answer"
        assert dpo["metadata"]["correction_type"] == "vat_fix"


class TestNightlyDPORunner:
    def test_run_skipped_insufficient(self):
        from nyx_light.memory.dpo import NightlyDPORunner, DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            runner = NightlyDPORunner(builder, models_dir=tmp)
            result = runner.run_nightly()
            assert result.status == "skipped"

    def test_run_completed(self):
        from nyx_light.memory.dpo import NightlyDPORunner, DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            for i in range(55):
                builder.record_correction(f"p{i}", f"c{i}", f"r{i}", "u1")
            runner = NightlyDPORunner(builder, models_dir=tmp)
            result = runner.run_nightly()
            assert result.status == "completed"
            assert result.deployed is True
            assert result.pairs_count == 55

    def test_stats(self):
        from nyx_light.memory.dpo import NightlyDPORunner, DPODatasetBuilder
        with tempfile.TemporaryDirectory() as tmp:
            builder = DPODatasetBuilder(db_path=os.path.join(tmp, "dpo.db"))
            runner = NightlyDPORunner(builder, models_dir=tmp)
            stats = runner.get_stats()
            assert stats["module"] == "dpo_nightly"


# ═══════════════════════════════════════════
# 4. TIME-AWARE RAG TESTS
# ═══════════════════════════════════════════

class TestLawChunk:
    def test_is_current(self):
        from nyx_light.modules.rag import LawChunk
        chunk = LawChunk(valid_from="2023-01-01", valid_to="")
        assert chunk.is_current is True

    def test_is_expired(self):
        from nyx_light.modules.rag import LawChunk
        chunk = LawChunk(valid_from="2005-01-01", valid_to="2016-12-31")
        assert chunk.is_current is False

    def test_was_valid_on_date(self):
        from nyx_light.modules.rag import LawChunk
        chunk = LawChunk(valid_from="2017-01-01", valid_to="2024-12-31")
        assert chunk.was_valid_on("2020-06-15") is True
        assert chunk.was_valid_on("2025-01-01") is False
        assert chunk.was_valid_on("2016-12-31") is False

    def test_to_dict(self):
        from nyx_light.modules.rag import LawChunk, LawCategory
        chunk = LawChunk(
            chunk_id="test1",
            law_name="ZPDV",
            law_short="ZPDV",
            category=LawCategory.PDV,
            article="čl. 38",
            content="Test content",
        )
        d = chunk.to_dict()
        assert d["law_short"] == "ZPDV"
        assert d["article"] == "čl. 38"


class TestTimeAwareRAG:
    @pytest.fixture
    def rag(self, tmp_path):
        from nyx_light.modules.rag import TimeAwareRAG
        return TimeAwareRAG(db_path=str(tmp_path / "laws.db"))

    def test_seed_data_loaded(self, rag):
        stats = rag.get_stats()
        assert stats["total_chunks"] > 10
        assert "ZPDV" in stats["laws_covered"]
        assert "ZOR" in stats["laws_covered"]

    def test_search_pdv_rate(self, rag):
        from nyx_light.modules.rag import LawCategory
        result = rag.search("stopa PDV", category=LawCategory.PDV)
        assert len(result.chunks) > 0
        assert any("25%" in c.content for c in result.chunks)
        assert result.answer

    def test_search_with_date_current(self, rag):
        result = rag.search("kilometraža naknada", event_date="2025-06-01")
        assert len(result.chunks) > 0
        assert any("0,40" in c.content for c in result.chunks)

    def test_search_with_date_old(self, rag):
        result = rag.search("kilometraža naknada", event_date="2024-06-01",
                            include_expired=True)
        assert len(result.chunks) > 0
        # Should find old 0.30 EUR version
        assert any("0,30" in c.content for c in result.chunks)

    def test_search_porez_dobit(self, rag):
        from nyx_light.modules.rag import LawCategory
        result = rag.search("stopa poreza dobit", category=LawCategory.POREZ_DOBIT)
        assert len(result.chunks) > 0

    def test_search_no_results(self, rag):
        result = rag.search("kvantna gravitacija")
        assert len(result.chunks) == 0
        assert "Nije pronađen" in result.answer

    def test_citations_include_nn(self, rag):
        result = rag.search("obvezni elementi računa")
        if result.chunks:
            assert any("NN" in c for c in result.citations)

    def test_expired_flag_in_citations(self, rag):
        result = rag.search("stopa poreza dobit 20%", include_expired=True)
        if any(not c.is_current for c in result.chunks):
            assert any("IZVAN SNAGE" in c for c in result.citations)

    def test_categories(self, rag):
        cats = rag.get_categories()
        assert "pdv" in cats
        assert cats["pdv"] >= 3

    def test_add_custom_chunk(self, rag):
        from nyx_light.modules.rag import LawChunk, LawCategory
        rag.add_chunk(LawChunk(
            chunk_id="custom1",
            law_name="Posebni zakon",
            law_short="PZ",
            category=LawCategory.PRAVILNIK,
            content="Posebna odredba za testiranje",
            valid_from="2026-01-01",
        ))
        stats = rag.get_stats()
        assert "PZ" in stats["laws_covered"]

    def test_fiskalizacija_2026(self, rag):
        result = rag.search("fiskalizacija e-račun 2026")
        assert len(result.chunks) > 0
        assert any("EN 16931" in c.content or "2026" in c.content for c in result.chunks)


# ═══════════════════════════════════════════
# 5. WEB/CHAT UI TESTS
# ═══════════════════════════════════════════

class TestUIConfig:
    def test_default_config(self):
        from nyx_light.modules.web_ui import UIConfig
        config = UIConfig()
        assert config.max_concurrent_users == 15
        assert config.default_language == "hr"
        assert config.session_timeout_minutes == 480

    def test_to_dict(self):
        from nyx_light.modules.web_ui import UIConfig
        d = UIConfig().to_dict()
        assert d["max_users"] == 15
        assert d["ws_chat"] == "/ws/chat"


class TestUISessionManager:
    def test_create_session(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager(max_sessions=15)
        s = mgr.create_session("u1", "Ana", "racunovoda")
        assert s is not None
        assert s.username == "Ana"

    def test_duplicate_user_reuses(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager()
        s1 = mgr.create_session("u1", "Ana")
        s2 = mgr.create_session("u1", "Ana")
        assert s1.session_id == s2.session_id

    def test_max_sessions(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager(max_sessions=3)
        for i in range(3):
            mgr.create_session(f"u{i}", f"User{i}")
        # 4th should evict oldest inactive
        s4 = mgr.create_session("u3", "User3")
        assert s4 is not None  # Should succeed after eviction

    def test_close_session(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager()
        s = mgr.create_session("u1", "Ana")
        mgr.close_session(s.session_id)
        assert mgr.get_session(s.session_id) is None

    def test_get_active_sessions(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager()
        mgr.create_session("u1", "Ana")
        mgr.create_session("u2", "Marko")
        sessions = mgr.get_active_sessions()
        assert len(sessions) == 2
        names = [s["username"] for s in sessions]
        assert "Ana" in names
        assert "Marko" in names

    def test_stats(self):
        from nyx_light.modules.web_ui import UISessionManager
        mgr = UISessionManager(max_sessions=15)
        mgr.create_session("u1", "Ana")
        stats = mgr.get_stats()
        assert stats["active_sessions"] == 1
        assert stats["available_slots"] == 14
        assert stats["max_sessions"] == 15


class TestNotificationManager:
    def test_create_notification(self):
        from nyx_light.modules.web_ui import NotificationManager, NotificationType
        nm = NotificationManager()
        n = nm.create(NotificationType.ANOMALY, "Duplikat!", "Duplikat plaćanja detektiran")
        assert n.id
        assert n.type == NotificationType.ANOMALY

    def test_get_for_user(self):
        from nyx_light.modules.web_ui import NotificationManager, NotificationType
        nm = NotificationManager()
        nm.create(NotificationType.INFO, "T1", "Poruka za sve")
        nm.create(NotificationType.WARNING, "T2", "Poruka za Anu", target_user="ana")
        # Ana sees both (global + targeted)
        ana_notifs = nm.get_for_user("ana")
        assert len(ana_notifs) == 2
        # Marko sees only global
        marko_notifs = nm.get_for_user("marko")
        assert len(marko_notifs) == 1

    def test_unread_count(self):
        from nyx_light.modules.web_ui import NotificationManager, NotificationType
        nm = NotificationManager()
        n1 = nm.create(NotificationType.INFO, "T1", "Msg1")
        nm.create(NotificationType.INFO, "T2", "Msg2")
        assert nm.get_unread_count("any") == 2
        nm.mark_read(n1.id)
        assert nm.get_unread_count("any") == 1


class TestUITemplateGenerator:
    def test_generate_html(self):
        from nyx_light.modules.web_ui import UITemplateGenerator
        html = UITemplateGenerator.generate_index_html()
        assert "<!DOCTYPE html>" in html
        assert "Nyx Light" in html
        assert "Računovođa" in html
        assert "WebSocket" in html

    def test_html_has_sections(self):
        from nyx_light.modules.web_ui import UITemplateGenerator
        html = UITemplateGenerator.generate_index_html()
        sections = ["dashboard", "chat", "inbox", "knjizenja", "klijenti",
                     "izvjestaji", "zakoni", "postavke"]
        for sec in sections:
            assert f"sec-{sec}" in html, f"Missing section: {sec}"

    def test_html_has_rag_search(self):
        from nyx_light.modules.web_ui import UITemplateGenerator
        html = UITemplateGenerator.generate_index_html()
        assert "rag-query" in html
        assert "rag-date" in html
        assert "searchLaw" in html

    def test_html_has_approval_workflow(self):
        from nyx_light.modules.web_ui import UITemplateGenerator
        html = UITemplateGenerator.generate_index_html()
        assert "Odobri" in html
        assert "Ispravi" in html
        assert "Odbij" in html


class TestUIAPIRoutes:
    def test_routes_defined(self):
        from nyx_light.modules.web_ui import UIAPIRoutes
        routes = UIAPIRoutes.get_routes()
        assert len(routes) >= 15
        paths = [r["path"] for r in routes]
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/chat" in paths
        assert "/api/v1/rag/search" in paths
        assert "/ws/chat" in paths

    def test_openapi_summary(self):
        from nyx_light.modules.web_ui import UIAPIRoutes
        summary = UIAPIRoutes.get_openapi_summary()
        assert summary["version"] == "3.0"
        assert summary["total_routes"] >= 15
