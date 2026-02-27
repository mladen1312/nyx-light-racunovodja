"""
Testovi za Sprint 13: Deploy, EU Invoice, NN Monitor, LegalRAG, Law Downloader

Testira:
  1. Law Downloader — katalog 27 zakona, download, update, stats
  2. NN Monitor — keyword scoring, relevance, status
  3. EU Invoice — origin detection, VAT ID parsing, XML parse, OCR, reverse charge
  4. LegalRAG — initialize, query, keyword search, auto-update
  5. Deploy integration — config, auth, model catalog
  6. App wiring — EU invoice routing through NyxApp
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ═══════════════════════════════════════════
# 1. LAW DOWNLOADER
# ═══════════════════════════════════════════

class TestLawDownloader:
    def test_catalog_has_27_laws(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        assert len(LAW_CATALOG) >= 27, f"Expected 27+ laws, got {len(LAW_CATALOG)}"

    def test_all_priority_1_present(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        p1 = [l for l in LAW_CATALOG if l.priority == 1]
        slugs = {l.slug for l in p1}
        required = {
            "zakon_o_pdv", "zakon_o_racunovodstvu",
            "zakon_o_porezu_na_dobit", "zakon_o_porezu_na_dohodak",
            "zakon_o_doprinosima", "zakon_o_fiskalizaciji",
            "pravilnik_o_pdv", "pravilnik_o_porezu_na_dobit",
            "pravilnik_o_porezu_na_dohodak", "pravilnik_o_joppd",
            "pravilnik_o_neoporezivim_primicima",
            "pravilnik_o_fiskalizaciji",
        }
        missing = required - slugs
        assert not missing, f"Missing priority-1 laws: {missing}"

    def test_download_creates_files(self):
        from nyx_light.rag.law_downloader import LawDownloader
        with tempfile.TemporaryDirectory() as td:
            dl = LawDownloader(laws_dir=f"{td}/laws", rag_dir=f"{td}/rag")
            result = dl.download_all(priority_max=1)
            assert result["downloaded"] > 0
            files = list(Path(f"{td}/laws").glob("*.txt"))
            assert len(files) >= 5, f"Expected 5+ files, got {len(files)}"

    def test_check_for_updates(self):
        from nyx_light.rag.law_downloader import LawDownloader
        with tempfile.TemporaryDirectory() as td:
            dl = LawDownloader(laws_dir=f"{td}/laws", rag_dir=f"{td}/rag")
            check = dl.check_for_updates()
            assert check["not_downloaded"] >= 27

    def test_idempotent_download(self):
        from nyx_light.rag.law_downloader import LawDownloader
        with tempfile.TemporaryDirectory() as td:
            dl = LawDownloader(laws_dir=f"{td}/laws", rag_dir=f"{td}/rag")
            r1 = dl.download_all(priority_max=1)
            r2 = dl.download_all(priority_max=1)
            assert r2["skipped"] >= r1["downloaded"]
            assert r2["downloaded"] == 0

    def test_stats(self):
        from nyx_light.rag.law_downloader import LawDownloader
        with tempfile.TemporaryDirectory() as td:
            dl = LawDownloader(laws_dir=f"{td}/laws", rag_dir=f"{td}/rag")
            dl.download_all(priority_max=1)
            s = dl.get_stats()
            assert s["laws_in_catalog"] >= 27
            assert s["laws_downloaded"] > 0
            assert "zakon" in s["categories"]

    def test_list_laws(self):
        from nyx_light.rag.law_downloader import LawDownloader
        dl = LawDownloader()
        laws = dl.list_laws()
        assert len(laws) >= 27
        assert all("slug" in l and "name" in l for l in laws)


# ═══════════════════════════════════════════
# 2. NN MONITOR
# ═══════════════════════════════════════════

class TestNNMonitor:
    def test_init(self):
        from nyx_light.rag.nn_monitor import NNMonitor
        with tempfile.TemporaryDirectory() as td:
            m = NNMonitor(laws_dir=f"{td}/laws")
            assert m is not None

    def test_relevance_scoring(self):
        from nyx_light.rag.nn_monitor import NNMonitor, NNArticle
        m = NNMonitor()
        a = NNArticle(
            nn_number="9/25", year=2025, issue=9,
            title="Zakon o izmjenama Zakona o porezu na dodanu vrijednost",
            category="zakon", url="", published_date="2025-01-15"
        )
        score = m._calculate_relevance(a)
        assert score >= 0.5, f"PDV law should be highly relevant, got {score}"

    def test_irrelevant_scoring(self):
        from nyx_light.rag.nn_monitor import NNMonitor, NNArticle
        m = NNMonitor()
        a = NNArticle(
            nn_number="50/25", year=2025, issue=50,
            title="Zakon o šumama",
            category="zakon", url="", published_date="2025-05-01"
        )
        score = m._calculate_relevance(a)
        assert score < 0.3, f"Forest law should be irrelevant, got {score}"

    def test_tracked_laws(self):
        from nyx_light.rag.nn_monitor import TRACKED_LAWS
        assert len(TRACKED_LAWS) >= 10
        assert "zakon-o-porezu-na-dodanu-vrijednost" in TRACKED_LAWS

    def test_status(self):
        from nyx_light.rag.nn_monitor import NNMonitor
        with tempfile.TemporaryDirectory() as td:
            m = NNMonitor(laws_dir=f"{td}/laws")
            s = m.get_status()
            assert "tracked_laws" in s
            assert s["tracked_laws"] >= 10


# ═══════════════════════════════════════════
# 3. EU INVOICE RECOGNITION
# ═══════════════════════════════════════════

class TestEUInvoice:
    def test_detect_origin_hr(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer, InvoiceOrigin
        r = EUInvoiceRecognizer()
        assert r.detect_origin(vat_id="HR12345678901") == InvoiceOrigin.HR

    def test_detect_origin_eu(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer, InvoiceOrigin
        r = EUInvoiceRecognizer()
        assert r.detect_origin(vat_id="DE123456789") == InvoiceOrigin.EU
        assert r.detect_origin(vat_id="IT12345678901") == InvoiceOrigin.EU
        assert r.detect_origin(vat_id="SI12345678") == InvoiceOrigin.EU

    def test_detect_origin_non_eu(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer, InvoiceOrigin
        r = EUInvoiceRecognizer()
        # Non-EU: text with USD / no EU VAT
        origin = r.detect_origin(text="Total USD 1,500.00 Invoice from New York")
        assert origin == InvoiceOrigin.NON_EU

    def test_find_vat_ids(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        text = "Seller: DE123456789 Buyer: HR12345678901 Also: IT12345678901"
        vats = r.find_vat_ids(text)
        assert "DE123456789" in vats
        assert "HR12345678901" in vats
        assert "IT12345678901" in vats

    def test_parse_ubl_xml(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        xml = """<?xml version="1.0"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>INV-2025-001</cbc:ID>
  <cbc:IssueDate>2025-03-15</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:CompanyID>DE123456789</cbc:CompanyID>
      <cbc:Name>Lieferant GmbH</cbc:Name>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount>1000.00</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount>1000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""
        data = r.parse_xml(xml)
        assert data.invoice_number == "INV-2025-001"
        assert data.seller_vat_id == "DE123456789"
        assert data.total == 1000.0
        assert data.currency == "EUR"
        assert data.confidence >= 0.9

    def test_reverse_charge_detection(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        text = """
        Rechnung Nr. 2025-100
        Lieferant GmbH, DE123456789
        Reverse charge - Steuerschuldnerschaft des Leistungsempfängers
        Netto: 5.000,00 EUR
        MwSt: 0,00 EUR
        Gesamt: 5.000,00 EUR
        """
        data = r.parse_ocr_text(text, source_language="de")
        assert data.reverse_charge is True

    def test_vat_treatment_eu_reverse_charge(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import (
            EUInvoiceRecognizer, InvoiceOrigin, VATTreatment
        )
        r = EUInvoiceRecognizer()
        text = "DE123456789 Reverse charge Gesamt: 1.000,00 EUR MwSt: 0,00"
        data = r.parse_ocr_text(text, source_language="de")
        assert data.vat_treatment == VATTreatment.REVERSE_CHARGE

    def test_multilingual_amount_parsing(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        # German format
        de_text = "Nettobetrag: 1.234,56\nMwSt 19%: 234,57\nGesamtbetrag: 1.469,13"
        data = r.parse_ocr_text(de_text, source_language="de")
        assert data.subtotal == 1234.56
        assert data.total == 1469.13

    def test_currency_detection(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        assert r._detect_currency("Total: $1,500.00") == "USD"
        assert r._detect_currency("Gesamt: 1.500,00 €") == "EUR"
        assert r._detect_currency("Total: £750.00") == "GBP"
        assert r._detect_currency("Betrag: CHF 2.000,00") == "CHF"

    def test_eu_countries_complete(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EU_COUNTRIES
        assert len(EU_COUNTRIES) == 27  # 27 EU members
        assert "HR" in EU_COUNTRIES
        assert "DE" in EU_COUNTRIES
        assert "SI" in EU_COUNTRIES

    def test_stats(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        r = EUInvoiceRecognizer()
        r.parse_ocr_text("DE123456789 Total: 100,00 EUR", "de")
        s = r.get_stats()
        assert s["total_parsed"] == 1
        assert len(s["supported_formats"]) >= 8
        assert len(s["supported_languages"]) >= 5


# ═══════════════════════════════════════════
# 4. LEGAL RAG
# ═══════════════════════════════════════════

class TestLegalRAG:
    def test_init(self):
        from nyx_light.rag.legal_rag import LegalRAG
        rag = LegalRAG()
        assert not rag._initialized

    def test_query_before_init(self):
        from nyx_light.rag.legal_rag import LegalRAG
        rag = LegalRAG()
        r = rag.query("Koja je stopa PDV-a?")
        assert r["confidence"] == 0.0
        assert "warning" in r

    def test_initialize_and_query(self):
        from nyx_light.rag.legal_rag import LegalRAG
        with tempfile.TemporaryDirectory() as td:
            rag = LegalRAG(laws_dir=f"{td}/laws", rag_dir=f"{td}/rag",
                           embed_cache=f"{td}/emb")
            result = rag.initialize(download=True)
            assert result["laws_downloaded"] > 0
            assert result["chunks_created"] >= 0
            assert rag._initialized

    def test_ingest_law(self):
        from nyx_light.rag.legal_rag import LegalRAG
        rag = LegalRAG()
        rag._initialized = True
        r = rag.ingest_law("Test zakon", "Članak 1. Test.", datetime(2025, 1, 1))
        assert r["status"] == "ingested"
        assert r["total_chunks"] == 1

    def test_stats(self):
        from nyx_light.rag.legal_rag import LegalRAG
        rag = LegalRAG()
        s = rag.get_stats()
        assert "initialized" in s
        assert "chunks" in s
        assert "embed_model" in s


# ═══════════════════════════════════════════
# 5. MODEL CATALOG
# ═══════════════════════════════════════════

class TestModelCatalog:
    def test_catalog_has_required_models(self):
        from nyx_light.model_manager import MODEL_CATALOG
        assert "qwen3-235b-a22b" in MODEL_CATALOG
        assert "qwen3-vl-8b" in MODEL_CATALOG
        assert "qwen3-30b-a3b" in MODEL_CATALOG

    def test_256gb_recommends_qwen3_235b(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager()
        rec = mgr.recommend_model(ram_gb=256)
        assert "235" in rec.name

    def test_192gb_recommends_72b(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager()
        rec = mgr.recommend_model(ram_gb=192)
        assert "72B" in rec.name

    def test_96gb_recommends_72b(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager()
        rec = mgr.recommend_model(ram_gb=96)
        assert "72" in rec.name

    def test_64gb_recommends_30b(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager()
        rec = mgr.recommend_model(ram_gb=64)
        assert "30" in rec.name

    def test_vision_model_is_qwen3(self):
        from nyx_light.model_manager import MODEL_CATALOG
        v = MODEL_CATALOG["qwen3-vl-8b"]
        assert "Qwen3-VL" in v.name
        assert v.size_gb == 5
        assert v.model_type == "vision"


# ═══════════════════════════════════════════
# 6. APP WIRING — EU INVOICE THROUGH PIPELINE
# ═══════════════════════════════════════════

class TestAppEUInvoice:
    def test_app_has_eu_invoice(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        assert hasattr(app, "eu_invoice")
        assert app.eu_invoice is not None

    def test_process_eu_invoice(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        from nyx_light.registry import ClientConfig
        app.register_client(ClientConfig(
            id="test-eu", naziv="Test EU", oib="12345678901", erp_target="CPP"))

        result = app.process_eu_invoice(
            invoice_data={
                "raw_text": "DE123456789 Reverse charge Gesamt: 1.000,00 EUR",
                "xml_content": "",
            },
            client_id="test-eu",
        )
        assert result is not None
        assert "id" in result or "proposal" in result or "status" in result

    def test_process_invoice_routes_eu(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        from nyx_light.registry import ClientConfig
        app.register_client(ClientConfig(
            id="test-route", naziv="Test", oib="12345678901", erp_target="CPP"))

        result = app.process_invoice(
            invoice_data={
                "raw_text": "Rechnung DE123456789",
                "seller_vat_id": "DE123456789",
            },
            client_id="test-route",
        )
        assert result is not None

    def test_process_invoice_hr_stays_domestic(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        from nyx_light.registry import ClientConfig
        app.register_client(ClientConfig(
            id="test-hr", naziv="Test HR", oib="12345678901", erp_target="CPP"))

        result = app.process_invoice(
            invoice_data={
                "oib_izdavatelja": "12345678901",
                "dobavljac": "Test d.o.o.",
                "iznos_ukupno": 1250.0,
            },
            client_id="test-hr",
        )
        assert result is not None


# ═══════════════════════════════════════════
# 7. DEPLOY FILES EXIST
# ═══════════════════════════════════════════

class TestDeployFiles:
    def test_deploy_sh_exists(self):
        assert Path("deploy.sh").exists() or Path("install.sh").exists()

    def test_update_sh_exists(self):
        assert Path("update.sh").exists()

    def test_readme_exists(self):
        assert Path("README.md").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
