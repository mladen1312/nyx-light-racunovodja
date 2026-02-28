"""
Tests: Universal Invoice Parser (Sprint 21)
════════════════════════════════════════════
Testira svih 5 tier-ova + legal validation + EU extension.
"""

import pytest
from decimal import Decimal


class TestXMLParsing:
    """Tier 1: eRačun XML parsing."""

    def _make_ubl_xml(self, **overrides) -> bytes:
        """Helper: generiraj UBL 2.1 XML."""
        from nyx_light.modules.fiskalizacija2 import (
            Fiskalizacija2Engine, FiskRacun, FiskStavka)
        engine = Fiskalizacija2Engine()
        defaults = dict(
            broj_racuna="TEST-2026-001",
            poslovni_prostor="PP1", naplatni_uredaj="NU1", redni_broj=1,
            datum_izdavanja="2026-02-28", datum_dospijeca="2026-03-30",
            izdavatelj_naziv="Dobavljač d.o.o.",
            izdavatelj_oib="12345678903",
            izdavatelj_adresa="Ilica 1", izdavatelj_grad="Zagreb",
            izdavatelj_postanski="10000",
            izdavatelj_iban="HR1234567890123456789",
            primatelj_naziv="Kupac d.o.o.",
            primatelj_oib="98765432106",
            primatelj_adresa="Savska 10", primatelj_grad="Split",
            primatelj_postanski="21000",
            stavke=[FiskStavka(opis="IT konzalting", kolicina=10,
                              jedinica="sat", cijena_bez_pdv=100, pdv_stopa=25)],
        )
        defaults.update(overrides)
        racun = FiskRacun(**defaults)
        xml = engine.generate_xml(racun)
        return xml.encode("utf-8")

    def test_detect_xml_invoice(self):
        from nyx_light.modules.universal_parser import XMLInvoiceParser
        xml = self._make_ubl_xml()
        assert XMLInvoiceParser.is_xml_invoice(xml)
        assert not XMLInvoiceParser.is_xml_invoice(b"Hello world")
        assert not XMLInvoiceParser.is_xml_invoice(b"%PDF-1.4")

    def test_parse_ubl_basic(self):
        from nyx_light.modules.universal_parser import XMLInvoiceParser, ParserTier
        xml = self._make_ubl_xml()
        invoice = XMLInvoiceParser.parse(xml)
        assert invoice.parser_tier == ParserTier.XML_ERACUN
        assert invoice.confidence >= 0.95
        assert invoice.invoice_number == "TEST-2026-001"
        assert invoice.supplier_oib == "12345678903"
        assert invoice.customer_oib == "98765432106"
        assert invoice.currency == "EUR"

    def test_parse_ubl_amounts(self):
        from nyx_light.modules.universal_parser import XMLInvoiceParser
        xml = self._make_ubl_xml()
        invoice = XMLInvoiceParser.parse(xml)
        assert invoice.net_total == Decimal("1000.00")
        assert invoice.gross_total == Decimal("1250.00")
        assert invoice.vat_total == Decimal("250.00")

    def test_parse_ubl_items(self):
        from nyx_light.modules.universal_parser import XMLInvoiceParser
        xml = self._make_ubl_xml()
        invoice = XMLInvoiceParser.parse(xml)
        assert len(invoice.items) == 1
        assert invoice.items[0].description == "IT konzalting"
        assert invoice.items[0].kpd_code != ""  # Auto-assigned by fisk2

    def test_parse_ubl_kpd_code(self):
        from nyx_light.modules.universal_parser import XMLInvoiceParser
        xml = self._make_ubl_xml()
        invoice = XMLInvoiceParser.parse(xml)
        assert invoice.items[0].kpd_code == "620200"

    def test_universal_parser_tier1(self):
        """UniversalInvoiceParser koristi Tier 1 za XML."""
        from nyx_light.modules.universal_parser import UniversalInvoiceParser, ParserTier
        parser = UniversalInvoiceParser()
        xml = self._make_ubl_xml()
        result = parser.parse(content=xml)
        assert result.parser_tier == ParserTier.XML_ERACUN
        assert result.validation_status.value == "valid"


class TestRegexExtraction:
    """Tier 3: Rule-based regex."""

    def test_extract_oib(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "OIB dobavljača: 12345678903, OIB kupca: 98765432106"
        result = RegexExtractor.extract(text)
        assert result.supplier_oib == "12345678903"
        assert result.customer_oib == "98765432106"

    def test_oib_validation_mod11(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        assert RegexExtractor._validate_oib("12345678903") == True
        assert RegexExtractor._validate_oib("11111111111") == False
        assert RegexExtractor._validate_oib("123") == False

    def test_extract_iban(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "IBAN: HR1234567890123456789"
        result = RegexExtractor.extract(text)
        assert result.supplier_iban == "HR1234567890123456789"

    def test_extract_dates_dmy(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "Datum: 28.02.2026 Rok plaćanja: 30.03.2026"
        result = RegexExtractor.extract(text)
        assert result.issue_date == "2026-02-28"
        assert result.due_date == "2026-03-30"

    def test_extract_dates_ymd(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "IssueDate: 2026-02-28"
        result = RegexExtractor.extract(text)
        assert result.issue_date == "2026-02-28"

    def test_extract_amounts_hr_format(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "Osnovica: 1.000,00 PDV: 250,00 Ukupno: 1.250,00"
        result = RegexExtractor.extract(text)
        assert result.gross_total == Decimal("1250.00")
        assert result.net_total == Decimal("1000.00")

    def test_extract_invoice_number(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "Račun br.: 2026/PP1/001"
        result = RegexExtractor.extract(text)
        assert "2026" in result.invoice_number

    def test_extract_jir(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "JIR: a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = RegexExtractor.extract(text)
        assert result.fiscal_code == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_confidence_score(self):
        from nyx_light.modules.universal_parser import RegexExtractor
        text = "OIB: 12345678903 Račun br. 001 Datum: 28.02.2026 Ukupno: 1.250,00"
        result = RegexExtractor.extract(text)
        assert result.confidence >= 0.6  # Has OIB, date, amount, inv number


class TestTemplateMatcher:
    """Tier 2: Template matching."""

    def test_match_by_oib(self):
        from nyx_light.modules.universal_parser import TemplateMatcher
        result = TemplateMatcher.match("", oib="81793146560")
        assert result is not None
        assert result["name"] == "HT"

    def test_match_by_pattern(self):
        from nyx_light.modules.universal_parser import TemplateMatcher
        result = TemplateMatcher.match("HRVATSKI TELEKOM d.d. Zagreb")
        assert result is not None
        assert result["name"] == "HT"

    def test_match_hep(self):
        from nyx_light.modules.universal_parser import TemplateMatcher
        result = TemplateMatcher.match("HEP-Opskrba d.o.o.")
        assert result is not None
        assert result["default_konto"] == "4110"

    def test_match_ina(self):
        from nyx_light.modules.universal_parser import TemplateMatcher
        result = TemplateMatcher.match("INA d.d. Zagreb, račun za gorivo")
        assert result is not None
        assert result["default_konto"] == "4070"

    def test_no_match(self):
        from nyx_light.modules.universal_parser import TemplateMatcher
        result = TemplateMatcher.match("Random company XYZ")
        assert result is None


class TestLegalValidation:
    """Tier 5: Legal validation — čl. 79 Zakona o PDV-u."""

    def test_valid_invoice(self):
        from nyx_light.modules.universal_parser import (
            ParsedInvoice, LegalValidator, ValidationStatus)
        inv = ParsedInvoice(
            invoice_number="2026-001", issue_date="2026-02-28",
            supplier_name="Test d.o.o.", supplier_oib="12345678903",
            customer_name="Kupac d.o.o.", customer_oib="98765432106",
            net_total=Decimal("1000"), vat_total=Decimal("250"),
            gross_total=Decimal("1250"),
        )
        result = LegalValidator.validate(inv)
        assert result.validation_status == ValidationStatus.VALID
        assert len(result.missing_fields) == 0

    def test_missing_oib(self):
        from nyx_light.modules.universal_parser import (
            ParsedInvoice, LegalValidator, ValidationStatus)
        inv = ParsedInvoice(
            invoice_number="2026-001", issue_date="2026-02-28",
            supplier_name="Test", supplier_oib="",
            customer_name="Kupac", customer_oib="98765432106",
            gross_total=Decimal("1250"),
        )
        result = LegalValidator.validate(inv)
        assert result.validation_status == ValidationStatus.NEEDS_REVIEW
        assert any("OIB dobavljača" in m for m in result.missing_fields)

    def test_balance_check(self):
        from nyx_light.modules.universal_parser import (
            ParsedInvoice, LegalValidator)
        inv = ParsedInvoice(
            invoice_number="001", issue_date="2026-02-28",
            supplier_name="A", supplier_oib="12345678903",
            customer_name="B", customer_oib="98765432106",
            net_total=Decimal("1000"), vat_total=Decimal("250"),
            gross_total=Decimal("1300"),  # WRONG!
        )
        result = LegalValidator.validate(inv)
        assert any("NERAVNOTEŽA" in m for m in result.missing_fields)

    def test_fisk2_kpd_warning(self):
        from nyx_light.modules.universal_parser import (
            ParsedInvoice, InvoiceItem, LegalValidator)
        inv = ParsedInvoice(
            invoice_number="001", issue_date="2026-06-15",
            supplier_name="A", supplier_oib="12345678903",
            customer_name="B", customer_oib="98765432106",
            gross_total=Decimal("1000"),
            items=[InvoiceItem(description="Test", kpd_code="")],
        )
        result = LegalValidator.validate(inv)
        assert any("KPD" in w for w in result.warnings)


class TestUniversalParserIntegration:
    """End-to-end parser tests."""

    def setup_method(self):
        from nyx_light.modules.universal_parser import UniversalInvoiceParser
        self.parser = UniversalInvoiceParser()

    def test_parse_ocr_text_ht(self):
        from nyx_light.modules.universal_parser import ParserTier
        text = """
        HRVATSKI TELEKOM d.d.
        OIB: 81793146560
        Račun br.: HT-2026/02-12345
        Datum: 15.02.2026
        
        Kupac: Moj Ured d.o.o.
        OIB: 98765432106
        
        Mjesečna pretplata   1   50,00  50,00
        Internet 100Mbps     1  100,00 100,00
        
        Osnovica: 150,00
        PDV 25%:   37,50
        Ukupno:   187,50
        
        IBAN: HR1234567890123456789
        """
        result = self.parser.parse(ocr_text=text)
        assert result.parser_tier == ParserTier.TEMPLATE
        assert result.supplier_name == "HT"
        assert result.supplier_oib == "81793146560"
        assert result.gross_total == Decimal("187.50")

    def test_parse_ocr_text_unknown_supplier(self):
        from nyx_light.modules.universal_parser import ParserTier
        text = """
        Mali Obrt Horvat
        OIB: 12345678903
        Račun br. 15/2026
        Datum: 01.02.2026
        
        Kupac: Firma d.o.o.
        OIB: 98765432106
        
        Usluga popravka   1   500,00   500,00
        PDV 25%: 125,00
        Ukupno: 625,00
        """
        result = self.parser.parse(ocr_text=text)
        assert result.parser_tier in (ParserTier.REGEX, ParserTier.LLM)
        assert result.supplier_oib == "12345678903"
        assert result.gross_total == Decimal("625.00")

    def test_parse_empty_content(self):
        from nyx_light.modules.universal_parser import ParserTier
        result = self.parser.parse(content=b"", ocr_text="")
        assert result.parser_tier == ParserTier.MANUAL
        assert result.confidence == 0.0

    def test_stats(self):
        self.parser.parse(ocr_text="OIB: 81793146560 Hrvatski Telekom Ukupno: 100,00")
        stats = self.parser.get_stats()
        assert stats["total_parsed"] >= 1

    def test_source_hash(self):
        result = self.parser.parse(ocr_text="Test content")
        assert result.source_hash != ""
        assert len(result.source_hash) == 16


class TestEUExtension:
    """EU country configs."""

    def test_hr_config(self):
        from nyx_light.modules.universal_parser import get_country_config
        hr = get_country_config("HR")
        assert hr["vat_rates"] == [25, 13, 5, 0]
        assert hr["tax_id_name"] == "OIB"

    def test_de_config(self):
        from nyx_light.modules.universal_parser import get_country_config
        de = get_country_config("DE")
        assert 19 in de["vat_rates"]
        assert de["tax_id_name"] == "USt-IdNr"

    def test_it_config(self):
        from nyx_light.modules.universal_parser import get_country_config
        it = get_country_config("IT")
        assert it["fiscal_required"] == True  # FatturaPA

    def test_unknown_country_defaults_to_hr(self):
        from nyx_light.modules.universal_parser import get_country_config
        unknown = get_country_config("XX")
        assert unknown["tax_id_name"] == "OIB"


class TestInvoiceItemCalculations:
    """Provjera izračuna na stavkama."""

    def test_calculated_total(self):
        from nyx_light.modules.universal_parser import InvoiceItem
        item = InvoiceItem(quantity=Decimal("10"), unit_price=Decimal("100"))
        assert item.calculated_total == Decimal("1000.00")

    def test_calculated_total_with_discount(self):
        from nyx_light.modules.universal_parser import InvoiceItem
        item = InvoiceItem(quantity=Decimal("10"), unit_price=Decimal("100"),
                          discount_pct=Decimal("10"))
        assert item.calculated_total == Decimal("900.00")

    def test_vat_amount(self):
        from nyx_light.modules.universal_parser import InvoiceItem
        item = InvoiceItem(quantity=Decimal("1"), unit_price=Decimal("100"),
                          vat_rate=Decimal("25"))
        assert item.vat_amount == Decimal("25.00")

    def test_vat_rate_13(self):
        from nyx_light.modules.universal_parser import InvoiceItem
        item = InvoiceItem(quantity=Decimal("1"), unit_price=Decimal("100"),
                          vat_rate=Decimal("13"))
        assert item.vat_amount == Decimal("13.00")
