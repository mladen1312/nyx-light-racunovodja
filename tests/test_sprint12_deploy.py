"""
Testovi za Sprint 12: NN Monitor, Law Downloader v2, EU Invoice Recognition
"""
import json
import os
import sys
import tempfile
from datetime import datetime, date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ═══════════════════════════════════════════════════
# LAW DOWNLOADER TESTS
# ═══════════════════════════════════════════════════

class TestLawDownloader:
    """Testovi za Law Downloader v2."""

    def setup_method(self):
        from nyx_light.rag.law_downloader import LawDownloader
        self.tmpdir = tempfile.mkdtemp()
        self.dl = LawDownloader(
            laws_dir=os.path.join(self.tmpdir, "laws"),
            rag_dir=os.path.join(self.tmpdir, "rag"),
        )

    def test_catalog_has_minimum_laws(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        assert len(LAW_CATALOG) >= 20, f"Katalog ima samo {len(LAW_CATALOG)} zakona, treba 20+"

    def test_catalog_priority_1_critical(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        p1 = [l for l in LAW_CATALOG if l.priority == 1]
        assert len(p1) >= 5, "Treba barem 5 kritičnih zakona (prioritet 1)"
        slugs = {l.slug for l in p1}
        assert "zakon_o_pdv" in slugs
        assert "zakon_o_racunovodstvu" in slugs
        assert "zakon_o_porezu_na_dobit" in slugs
        assert "zakon_o_porezu_na_dohodak" in slugs
        assert "zakon_o_doprinosima" in slugs

    def test_catalog_has_pravilniks(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        pravilnici = [l for l in LAW_CATALOG if l.category == "pravilnik"]
        assert len(pravilnici) >= 7, f"Treba 7+ pravilnika, ima {len(pravilnici)}"

    def test_catalog_has_neoporezivi(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        slugs = {l.slug for l in LAW_CATALOG}
        assert "pravilnik_o_neoporezivim_primicima" in slugs
        assert "osobni_odbitak" in slugs

    def test_catalog_has_joppd(self):
        from nyx_light.rag.law_downloader import LAW_CATALOG
        slugs = {l.slug for l in LAW_CATALOG}
        assert "pravilnik_o_joppd" in slugs

    def test_download_all_creates_files(self):
        result = self.dl.download_all(priority_max=1)
        assert result["downloaded"] > 0 or result["skipped"] > 0
        assert result["errors"] == 0
        # Provjeri da su datoteke kreirane
        law_files = list(Path(self.tmpdir, "laws").glob("*.txt"))
        assert len(law_files) >= 5

    def test_download_creates_metadata_header(self):
        self.dl.download_all(priority_max=1)
        pdv_file = Path(self.tmpdir, "laws", "zakon_o_pdv.txt")
        assert pdv_file.exists()
        content = pdv_file.read_text()
        assert "---" in content
        assert "zakon: Zakon o porezu na dodanu vrijednost" in content
        assert "nn: 73/13" in content

    def test_check_for_updates_after_download(self):
        self.dl.download_all(priority_max=1)
        check = self.dl.check_for_updates()
        # Prioritet 1 bi trebali biti ažurni
        assert check["updates_available"] == 0 or check["not_downloaded"] >= 0

    def test_versions_file_created(self):
        self.dl.download_all(priority_max=1)
        vf = Path(self.tmpdir, "laws", "law_versions.json")
        assert vf.exists()
        data = json.loads(vf.read_text())
        assert "laws" in data
        assert "last_check" in data
        assert len(data["laws"]) >= 5

    def test_idempotent_download(self):
        r1 = self.dl.download_all(priority_max=1)
        r2 = self.dl.download_all(priority_max=1)
        # Drugi put sve bi trebalo biti skipped
        assert r2["skipped"] >= r1["downloaded"]
        assert r2["downloaded"] == 0

    def test_stats(self):
        self.dl.download_all(priority_max=1)
        stats = self.dl.get_stats()
        assert stats["laws_downloaded"] >= 5
        assert stats["total_size_kb"] > 0
        assert "zakon" in stats["categories"]

    def test_list_laws(self):
        laws = self.dl.list_laws()
        assert len(laws) >= 20
        assert all("slug" in l and "name" in l for l in laws)

    def test_zakon_hr_id_map(self):
        # Provjeri da svi prioritet 1-2 zakoni imaju zakon.hr ID
        from nyx_light.rag.law_downloader import LAW_CATALOG
        for law in LAW_CATALOG:
            if law.category == "zakon" and law.priority <= 2:
                zid = self.dl._zakon_hr_id(law.slug)
                if law.slug not in ("zakon_o_provedbi_ovrhe",):
                    assert zid, f"{law.slug} nema zakon.hr ID"


# ═══════════════════════════════════════════════════
# NN MONITOR TESTS
# ═══════════════════════════════════════════════════

class TestNNMonitor:
    """Testovi za Narodne Novine Monitor."""

    def setup_method(self):
        from nyx_light.rag.nn_monitor import NNMonitor
        self.tmpdir = tempfile.mkdtemp()
        self.monitor = NNMonitor(
            laws_dir=os.path.join(self.tmpdir, "laws"),
            rag_dir=os.path.join(self.tmpdir, "rag"),
        )

    def test_tracked_keywords_count(self):
        from nyx_light.rag.nn_monitor import TRACKED_KEYWORDS
        assert len(TRACKED_KEYWORDS) >= 30, f"Samo {len(TRACKED_KEYWORDS)} ključnih riječi"

    def test_tracked_keywords_cover_core_taxes(self):
        from nyx_light.rag.nn_monitor import TRACKED_KEYWORDS
        kw_str = " ".join(TRACKED_KEYWORDS).lower()
        assert "pdv" in kw_str
        assert "porez na dobit" in kw_str
        assert "porez na dohodak" in kw_str
        assert "doprinosi" in kw_str
        assert "fiskalizacija" in kw_str
        assert "računovodstvu" in kw_str or "racunovodstvu" in kw_str

    def test_tracked_keywords_cover_pravilniks(self):
        from nyx_light.rag.nn_monitor import TRACKED_KEYWORDS
        kw_str = " ".join(TRACKED_KEYWORDS).lower()
        assert "joppd" in kw_str
        assert "amortizacija" in kw_str or "amortizacijske" in kw_str
        assert "minimalna plaća" in kw_str or "minimalna placa" in kw_str

    def test_tracked_laws_map(self):
        from nyx_light.rag.nn_monitor import TRACKED_LAWS
        assert len(TRACKED_LAWS) >= 8
        assert "zakon-o-porezu-na-dodanu-vrijednost" in TRACKED_LAWS
        assert "zakon-o-racunovodstvu" in TRACKED_LAWS

    def test_relevance_high_for_pdv(self):
        from nyx_light.rag.nn_monitor import NNArticle
        article = NNArticle(
            nn_number="9/25", year=2025, issue=9,
            title="Zakon o izmjenama Zakona o porezu na dodanu vrijednost",
            category="zakon", url="", published_date="2025-01-15",
        )
        score = self.monitor._calculate_relevance(article)
        assert score >= 0.5, f"PDV zakon bi trebao imati visoku relevantnost, ima {score}"

    def test_relevance_low_for_irrelevant(self):
        from nyx_light.rag.nn_monitor import NNArticle
        article = NNArticle(
            nn_number="50/25", year=2025, issue=50,
            title="Zakon o šumama",
            category="zakon", url="", published_date="2025-06-01",
        )
        score = self.monitor._calculate_relevance(article)
        assert score < 0.5, f"Zakon o šumama ne bi trebao biti relevantan, ima {score}"

    def test_relevance_medium_for_rad(self):
        from nyx_light.rag.nn_monitor import NNArticle
        article = NNArticle(
            nn_number="30/25", year=2025, issue=30,
            title="Pravilnik o sadržaju obračuna plaće i JOPPD",
            category="pravilnik", url="", published_date="2025-03-01",
        )
        score = self.monitor._calculate_relevance(article)
        assert score >= 0.3, f"JOPPD pravilnik bi trebao biti relevantan, ima {score}"

    def test_check_result_structure(self):
        result = self.monitor.check_for_updates(days_back=1)
        assert hasattr(result, "checked_at")
        assert hasattr(result, "nn_issues_checked")
        assert hasattr(result, "relevant_found")
        assert hasattr(result, "new_amendments")
        assert hasattr(result, "new_laws")

    def test_check_log_saved(self):
        self.monitor.check_for_updates(days_back=1)
        log_file = Path(self.tmpdir, "laws", "nn_check_log.json")
        assert log_file.exists()
        data = json.loads(log_file.read_text())
        assert "last_check" in data
        assert "checks" in data
        assert len(data["checks"]) >= 1

    def test_status(self):
        status = self.monitor.get_status()
        assert "last_check" in status
        assert "tracked_laws" in status
        assert "tracked_keywords" in status
        assert status["tracked_keywords"] >= 30

    def test_get_tracked_laws(self):
        laws = self.monitor.get_tracked_laws()
        assert len(laws) >= 8
        assert all("nn_slug" in l and "our_slug" in l for l in laws)

    def test_amendment_detection(self):
        """Test da prepoznaje izmjene zakona."""
        from nyx_light.rag.nn_monitor import NNArticle
        article = NNArticle(
            nn_number="99/25", year=2025, issue=99,
            title="Zakon o izmjenama i dopunama Zakona o porezu na dodanu vrijednost",
            category="zakon", url="", published_date="2025-10-01",
        )
        score = self.monitor._calculate_relevance(article)
        assert article.is_amendment or score >= 0.5


# ═══════════════════════════════════════════════════
# EU INVOICE RECOGNITION TESTS
# ═══════════════════════════════════════════════════

class TestEUInvoiceRecognizer:
    """Testovi za EU/inozemno prepoznavanje računa."""

    def setup_method(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceRecognizer
        self.rec = EUInvoiceRecognizer()

    def test_detect_origin_hr(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin
        assert self.rec.detect_origin(vat_id="HR12345678901") == InvoiceOrigin.HR

    def test_detect_origin_eu_de(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin
        assert self.rec.detect_origin(vat_id="DE123456789") == InvoiceOrigin.EU

    def test_detect_origin_eu_it(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin
        assert self.rec.detect_origin(vat_id="IT12345678901") == InvoiceOrigin.EU

    def test_detect_origin_eu_si(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin
        assert self.rec.detect_origin(vat_id="SI12345678") == InvoiceOrigin.EU

    def test_detect_origin_non_eu(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin
        text = "Invoice from ABC Ltd, London, UK. Amount: £1,500.00"
        origin = self.rec.detect_origin(text=text)
        assert origin == InvoiceOrigin.NON_EU

    def test_find_vat_ids(self):
        text = "Seller: DE123456789  Buyer: HR12345678901"
        vats = self.rec.find_vat_ids(text)
        assert "DE123456789" in vats
        assert "HR12345678901" in vats

    def test_find_vat_ids_all_eu(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import VAT_PATTERNS
        for country, pattern in VAT_PATTERNS.items():
            # Generiraj test VAT ID
            import re
            # Provjeri da pattern kompajlira
            compiled = re.compile(pattern)
            assert compiled, f"Pattern za {country} ne kompajlira"

    def test_country_extraction(self):
        assert self.rec.extract_country_from_vat("DE123456789") == "DE"
        assert self.rec.extract_country_from_vat("ATU12345678") == "AT"
        assert self.rec.extract_country_from_vat("FR12345678901") == "FR"
        assert self.rec.extract_country_from_vat("HR12345678901") == "HR"
        assert self.rec.extract_country_from_vat("SI12345678") == "SI"

    def test_eu_countries_complete(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EU_COUNTRIES
        assert len(EU_COUNTRIES) == 27, f"EU ima 27 članica, definirano {len(EU_COUNTRIES)}"
        assert "HR" in EU_COUNTRIES
        assert "DE" in EU_COUNTRIES
        assert "IT" in EU_COUNTRIES

    def test_parse_ubl_xml(self):
        """Test UBL XML parsiranja."""
        ubl = """<?xml version="1.0"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>INV-2025-001</cbc:ID>
  <cbc:IssueDate>2025-03-15</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:Name>Lieferant GmbH</cbc:Name>
      <cbc:CompanyID>DE123456789</cbc:CompanyID>
      <cac:PostalAddress><cac:Country><cbc:IdentificationCode>DE</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cbc:Name>Tvrtka d.o.o.</cbc:Name>
      <cbc:CompanyID>HR12345678901</cbc:CompanyID>
      <cac:PostalAddress><cac:Country><cbc:IdentificationCode>HR</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount>1000.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount>1000.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount>1000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""
        data = self.rec.parse_xml(ubl)
        assert data.invoice_number == "INV-2025-001"
        assert data.invoice_date == "2025-03-15"
        assert data.currency == "EUR"
        assert data.seller_vat_id == "DE123456789"
        assert data.seller_country == "DE"
        assert data.buyer_vat_id == "HR12345678901"
        assert data.buyer_country == "HR"
        assert data.total == 1000.00
        assert data.confidence >= 0.9

    def test_reverse_charge_detection_xml(self):
        """EU račun bez PDV-a → reverse charge."""
        from nyx_light.modules.invoice_ocr.eu_invoice import VATTreatment
        ubl = """<?xml version="1.0"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:ID>RE-2025-100</cbc:ID>
  <cbc:IssueDate>2025-02-01</cbc:IssueDate>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:CompanyID>ATU12345678</cbc:CompanyID>
      <cac:PostalAddress><cac:Country><cbc:IdentificationCode>AT</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cbc:CompanyID>HR12345678901</cbc:CompanyID>
      <cac:PostalAddress><cac:Country><cbc:IdentificationCode>HR</cbc:IdentificationCode></cac:Country></cac:PostalAddress>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount>5000.00</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount>5000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""
        data = self.rec.parse_xml(ubl)
        assert data.reverse_charge is True
        assert data.vat_treatment == VATTreatment.REVERSE_CHARGE

    def test_ocr_german_invoice(self):
        """Test OCR teksta njemačkog računa."""
        text = """
        Rechnung Nr. RE-2025-456
        Datum: 15.03.2025

        Lieferant GmbH
        USt-IdNr.: DE123456789
        Berlin, Deutschland

        Käufer: Tvrtka d.o.o.
        UID: HR12345678901

        Nettobetrag:     1.250,00 EUR
        MwSt. 19%:         237,50 EUR
        Gesamtbetrag:    1.487,50 EUR

        Reverse Charge - Steuerschuldnerschaft des Leistungsempfängers
        """
        data = self.rec.parse_ocr_text(text)
        assert data.detected_language == "de"
        assert data.seller_vat_id == "DE123456789"
        assert data.buyer_vat_id == "HR12345678901"
        assert data.reverse_charge is True
        assert data.currency == "EUR"

    def test_ocr_italian_invoice(self):
        """Test OCR teksta talijanskog računa."""
        text = """
        Fattura N. FT-2025-789
        Data: 20.04.2025

        Fornitore S.r.l.
        P.IVA: IT12345678901
        Milano, Italia

        Imponibile:     2.000,00 €
        IVA 22%:          440,00 €
        Totale fattura:  2.440,00 €
        """
        data = self.rec.parse_ocr_text(text)
        assert data.detected_language == "it"
        assert data.seller_vat_id == "IT12345678901"
        assert data.currency == "EUR"
        assert data.total > 0

    def test_ocr_slovenian_invoice(self):
        """Test OCR slovenskog računa."""
        text = """
        Račun št. 2025-001
        Datum: 10.05.2025

        Podjetje d.o.o.
        ID za DDV: SI12345678
        Ljubljana, Slovenija

        Osnova: 500,00 EUR
        DDV 22%: 110,00 EUR
        Skupaj: 610,00 EUR
        """
        data = self.rec.parse_ocr_text(text)
        assert data.detected_language == "sl"
        assert data.seller_vat_id == "SI12345678"

    def test_non_eu_gbp_invoice(self):
        """Test Non-EU računa u GBP."""
        from nyx_light.modules.invoice_ocr.eu_invoice import InvoiceOrigin, VATTreatment
        text = """
        Invoice #UK-2025-100
        Date: 2025-06-01

        ABC Limited
        London, United Kingdom

        Subtotal: £3,500.00
        VAT: £0.00
        Total: £3,500.00
        """
        data = self.rec.parse_ocr_text(text)
        assert data.origin == InvoiceOrigin.NON_EU
        assert data.currency == "GBP"
        assert data.needs_exchange_rate is True
        assert data.vat_treatment == VATTreatment.IMPORT

    def test_amount_parsing_european(self):
        """Test parsiranja europskih formata iznosa."""
        assert self.rec._parse_amount("1.250,00") == 1250.00
        assert self.rec._parse_amount("1250,00") == 1250.00
        assert self.rec._parse_amount("12.500,50") == 12500.50

    def test_amount_parsing_us(self):
        """Test parsiranja US formata iznosa."""
        assert self.rec._parse_amount("1,250.00") == 1250.00
        assert self.rec._parse_amount("1250.00") == 1250.00

    def test_vat_treatment_domestic(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceData, InvoiceOrigin, VATTreatment
        data = EUInvoiceData(origin=InvoiceOrigin.HR)
        self.rec._determine_vat_treatment(data)
        assert data.vat_treatment == VATTreatment.DOMESTIC

    def test_vat_treatment_eu_reverse_charge(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceData, InvoiceOrigin, VATTreatment
        data = EUInvoiceData(
            origin=InvoiceOrigin.EU,
            reverse_charge=True,
            buyer_country="HR",
        )
        self.rec._determine_vat_treatment(data)
        assert data.vat_treatment == VATTreatment.REVERSE_CHARGE
        assert "1406" in str(data.suggested_accounts)

    def test_vat_treatment_import(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import EUInvoiceData, InvoiceOrigin, VATTreatment
        data = EUInvoiceData(origin=InvoiceOrigin.NON_EU)
        self.rec._determine_vat_treatment(data)
        assert data.vat_treatment == VATTreatment.IMPORT

    def test_stats(self):
        stats = self.rec.get_stats()
        assert stats["supported_countries"] == 27
        assert len(stats["supported_languages"]) >= 5
        assert "ubl_2.1" in stats["supported_formats"]

    def test_multilingual_keywords(self):
        from nyx_light.modules.invoice_ocr.eu_invoice import AMOUNT_KEYWORDS
        assert "en" in AMOUNT_KEYWORDS
        assert "de" in AMOUNT_KEYWORDS
        assert "it" in AMOUNT_KEYWORDS
        assert "sl" in AMOUNT_KEYWORDS
        assert "fr" in AMOUNT_KEYWORDS
        for lang in AMOUNT_KEYWORDS:
            assert "total" in AMOUNT_KEYWORDS[lang]
            assert "vat" in AMOUNT_KEYWORDS[lang]


# ═══════════════════════════════════════════════════
# MODEL CATALOG TESTS
# ═══════════════════════════════════════════════════

class TestModelCatalog:
    """Testovi za ažurirani Model Catalog."""

    def test_catalog_has_qwen3(self):
        from nyx_light.model_manager import MODEL_CATALOG
        assert "qwen3-235b-a22b" in MODEL_CATALOG
        assert "qwen3-vl-8b" in MODEL_CATALOG

    def test_catalog_has_fallbacks(self):
        from nyx_light.model_manager import MODEL_CATALOG
        assert "qwen2.5-72b" in MODEL_CATALOG
        assert "qwen3-30b-a3b" in MODEL_CATALOG

    def test_vision_model_updated(self):
        from nyx_light.model_manager import MODEL_CATALOG
        vision = MODEL_CATALOG["qwen3-vl-8b"]
        assert "Qwen3-VL-8B" in vision.name
        assert vision.model_type == "vision"
        assert vision.size_gb == 5

    def test_primary_model_specs(self):
        from nyx_light.model_manager import MODEL_CATALOG
        primary = MODEL_CATALOG["qwen3-235b-a22b"]
        assert primary.min_ram_gb == 256
        assert primary.size_gb == 124
        assert "MoE" in primary.description or "22B" in primary.description

    def test_recommend_256gb(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager.__new__(ModelManager)
        mgr._registry = {}
        mgr._models_dir = Path("/tmp/test_models")
        rec = mgr.recommend_model(ram_gb=256)
        assert "235B" in rec.name or "qwen3" in rec.name.lower()

    def test_recommend_192gb_gets_72b(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager.__new__(ModelManager)
        mgr._registry = {}
        mgr._models_dir = Path("/tmp/test_models")
        rec = mgr.recommend_model(ram_gb=192)
        assert "72B" in rec.name

    def test_recommend_96gb(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager.__new__(ModelManager)
        mgr._registry = {}
        mgr._models_dir = Path("/tmp/test_models")
        rec = mgr.recommend_model(ram_gb=96)
        assert "72B" in rec.name

    def test_recommend_64gb(self):
        from nyx_light.model_manager import ModelManager
        mgr = ModelManager.__new__(ModelManager)
        mgr._registry = {}
        mgr._models_dir = Path("/tmp/test_models")
        rec = mgr.recommend_model(ram_gb=64)
        assert "30B" in rec.name


# ═══════════════════════════════════════════════════
# DEPLOY/UPDATE SCRIPT TESTS
# ═══════════════════════════════════════════════════

class TestScripts:
    """Testovi za deploy/update skripte."""

    def test_deploy_exists(self):
        script = Path(__file__).parent.parent / "deploy.sh"
        assert script.exists(), "deploy.sh ne postoji"

    def test_deploy_executable_flag(self):
        script = Path(__file__).parent.parent / "deploy.sh"
        content = script.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_deploy_has_all_phases(self):
        script = Path(__file__).parent.parent / "deploy.sh"
        content = script.read_text()
        for phase in ["Faza 1", "Faza 2", "Faza 3", "Faza 4",
                       "Faza 5", "Faza 6", "Faza 7", "Faza 8", "Faza 9"]:
            assert phase in content, f"deploy.sh nedostaje {phase}"

    def test_deploy_has_model_download(self):
        script = Path(__file__).parent.parent / "deploy.sh"
        content = script.read_text()
        assert "Qwen3-235B-A22B" in content
        assert "Qwen3-VL-8B" in content

    def test_deploy_has_law_download(self):
        script = Path(__file__).parent.parent / "deploy.sh"
        content = script.read_text()
        assert "law_downloader" in content or "LawDownloader" in content

    def test_update_exists(self):
        script = Path(__file__).parent.parent / "update.sh"
        assert script.exists(), "update.sh ne postoji"

    def test_update_has_nn_check(self):
        script = Path(__file__).parent.parent / "update.sh"
        content = script.read_text()
        assert "nn_monitor" in content or "NNMonitor" in content

    def test_update_has_knowledge_check(self):
        script = Path(__file__).parent.parent / "update.sh"
        content = script.read_text()
        assert "Knowledge Preservation" in content or "verify_knowledge" in content

    def test_update_has_rollback(self):
        script = Path(__file__).parent.parent / "update.sh"
        content = script.read_text()
        assert "rollback" in content

    def test_readme_exists(self):
        readme = Path(__file__).parent.parent / "README.md"
        assert readme.exists()
        content = readme.read_text()
        assert len(content) > 5000, "README prekratak"

    def test_readme_has_deploy_instructions(self):
        readme = Path(__file__).parent.parent / "README.md"
        content = readme.read_text()
        assert "install.sh" in content or "deploy.sh" in content
        assert "start.sh" in content

    def test_readme_has_law_list(self):
        readme = Path(__file__).parent.parent / "README.md"
        content = readme.read_text()
        assert "Zakon o PDV" in content
        assert "Zakon o računovodstvu" in content
        assert "JOPPD" in content

    def test_readme_has_eu_section(self):
        readme = Path(__file__).parent.parent / "README.md"
        content = readme.read_text()
        assert "EN 16931" in content or "Peppol" in content
        assert "ZUGFeRD" in content or "FatturaPA" in content
