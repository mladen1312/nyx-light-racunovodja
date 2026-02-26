"""
Tests: Invoice OCR — robusni regex parser za HR račune.
Testira OIB validaciju, multi-PDV, datume, cross-validaciju, eRačun XML.
"""
import os
import tempfile
import pytest
from datetime import date


class TestOIBValidation:
    """OIB checksum validacija (ISO 7064, MOD 11,10)."""

    def test_valid_oib(self):
        from nyx_light.modules.invoice_ocr.extractor import validate_oib
        # Poznati valjani OIB-ovi (izračunati po algoritmu)
        assert validate_oib("94aborvt231") is False  # slova
        assert validate_oib("1234567890") is False   # prekratak
        assert validate_oib("123456789012") is False  # predug
        assert validate_oib("") is False

    def test_checksum_algorithm(self):
        from nyx_light.modules.invoice_ocr.extractor import validate_oib
        # OIB "69435151530" → checksum se računa: a=10, petlja kroz 10 digits
        # Testiram s poznatim algoritmom
        # Generiram validan OIB ručno
        def make_valid_oib(first10: str) -> str:
            a = 10
            for d in first10:
                a = (a + int(d)) % 10
                if a == 0: a = 10
                a = (a * 2) % 11
            ctrl = 11 - a
            if ctrl == 10: ctrl = 0
            return first10 + str(ctrl)
        
        oib = make_valid_oib("1234567890")
        assert validate_oib(oib) is True
        # Promijeni zadnju znamenku → invalid
        bad = oib[:10] + str((int(oib[10]) + 1) % 10)
        assert validate_oib(bad) is False


class TestAmountParsing:
    """Parsiranje iznosa u svim HR formatima."""

    def setup_method(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        self.ext = InvoiceExtractor()

    def test_hr_format(self):
        assert self.ext._parse_hr_amount("1.250,00") == 1250.00

    def test_hr_large(self):
        assert self.ext._parse_hr_amount("125.750,50") == 125750.50

    def test_simple_comma(self):
        assert self.ext._parse_hr_amount("250,00") == 250.00

    def test_en_format(self):
        assert self.ext._parse_hr_amount("1,250.00") == 1250.00

    def test_no_separator(self):
        assert self.ext._parse_hr_amount("250.00") == 250.00

    def test_invalid(self):
        assert self.ext._parse_hr_amount("abc") == 0.0


class TestDateParsing:
    """Parsiranje datuma u svim formatima."""

    def setup_method(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        self.ext = InvoiceExtractor()

    def test_dd_mm_yyyy_dot(self):
        d = self.ext._parse_first_date("Datum: 15.02.2026")
        assert d == date(2026, 2, 15)

    def test_dd_mm_yyyy_slash(self):
        d = self.ext._parse_first_date("Date: 15/02/2026")
        assert d == date(2026, 2, 15)

    def test_yyyy_mm_dd(self):
        d = self.ext._parse_first_date("Issued: 2026-02-15")
        assert d == date(2026, 2, 15)

    def test_dd_mm_yy(self):
        d = self.ext._parse_first_date("Datum: 15.02.26")
        assert d == date(2026, 2, 15)

    def test_date_with_spaces(self):
        d = self.ext._parse_first_date("15. 02. 2026")
        assert d == date(2026, 2, 15)


class TestFullInvoiceExtraction:
    """Ekstrakcija kompletnog računa iz teksta."""

    def setup_method(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        self.ext = InvoiceExtractor()

    def _make_valid_oib(self, first10="1234567890"):
        a = 10
        for d in first10:
            a = (a + int(d)) % 10
            if a == 0: a = 10
            a = (a * 2) % 11
        ctrl = 11 - a
        if ctrl == 10: ctrl = 0
        return first10 + str(ctrl)

    def test_standard_hr_invoice(self):
        oib = self._make_valid_oib("1234567890")
        text = f"""
PRIMJER D.O.O.
Ulica Grada Vukovara 123, Zagreb
OIB: {oib}

RAČUN br. R1-0042/1/2026

Datum računa: 15.02.2026
Datum dospijeća: 15.03.2026
Datum isporuke: 14.02.2026

Usluga programiranja     1.000,00 EUR
Usluga dizajna             500,00 EUR

Osnovica 25%:            1.500,00 EUR
PDV 25%:                   375,00 EUR
Ukupno za platiti:       1.875,00 EUR

IBAN: HR1234567890123456789
Model: HR00
Poziv na broj: HR00 12345-02-2026

JIR: a1b2c3d4-e5f6-7890-abcd-ef1234567890
ZKI: a1b2c3d4e5f67890abcdef1234567890
        """
        result = self.ext.extract_from_text(text)

        assert result["oib"] == oib
        assert result["oib_valid"] is True
        assert result["broj_racuna"] == "R1-0042/1/2026"
        assert result["datum"] == "2026-02-15"
        assert result["datum_dospijeca"] == "2026-03-15"
        assert result["ukupno"] == 1875.00
        assert result["pdv_ukupno"] == 375.00
        assert result["osnovica"] == 1500.00
        assert result["iban"] == "HR1234567890123456789"
        assert result["cross_validation_ok"] is True
        assert result["confidence"] >= 0.9

    def test_multi_pdv_invoice(self):
        oib = self._make_valid_oib("9876543210")
        text = f"""
TRGOVINA D.D.
OIB: {oib}

Račun broj: 2024-001234

Datum računa: 20.01.2026

Osnovica 25%:     800,00 EUR
PDV 25%:          200,00 EUR

Osnovica 13%:     400,00 EUR
PDV 13%:           52,00 EUR

Osnovica 5%:      100,00 EUR
PDV 5%:             5,00 EUR

Ukupno:         1.557,00 EUR

IBAN: HR9988776655443322110
        """
        result = self.ext.extract_from_text(text)

        assert result["oib"] == oib
        assert result["oib_valid"] is True
        assert len(result["pdv_stavke"]) == 3
        stope = {s["stopa"] for s in result["pdv_stavke"]}
        assert stope == {25.0, 13.0, 5.0}
        assert result["ukupno"] == 1557.00
        assert result["confidence"] >= 0.85

    def test_r2_invoice(self):
        oib = self._make_valid_oib("5555555550")
        text = f"""
MALI OBRT
OIB: {oib}
R-2 račun

Broj računa: 15/2026
Datum: 10.02.2026

Usluge čišćenja
Ukupno: 500,00 EUR
        """
        result = self.ext.extract_from_text(text)
        assert result["oib"] == oib
        assert result["tip_racuna"] == "R2"
        assert result["ukupno"] == 500.00

    def test_english_format_invoice(self):
        oib = self._make_valid_oib("1111111110")
        text = f"""
INTERNATIONAL CORP D.O.O.
OIB: {oib}

Invoice no. INV-2026-0099

Invoice date: 2026-02-15
Due date: 2026-03-15

Total: 2,500.00 EUR

IBAN: HR1122334455667788990
        """
        result = self.ext.extract_from_text(text)
        assert result["oib"] == oib
        assert result["broj_racuna"] == "INV-2026-0099"
        assert result["datum"] == "2026-02-15"
        assert result["ukupno"] == 2500.00

    def test_minimal_invoice_lower_confidence(self):
        text = """
Račun br. 42
Ukupno: 100,00 EUR
        """
        result = self.ext.extract_from_text(text)
        assert result["ukupno"] == 100.00
        assert result["confidence"] < 0.7  # Nedostaju OIB, datum, IBAN
        assert len(result["warnings"]) > 0

    def test_empty_text_zero_confidence(self):
        result = self.ext.extract_from_text("")
        assert result["confidence"] == 0.0

    def test_cross_validation_failure(self):
        oib = self._make_valid_oib("2222222220")
        text = f"""
FIRMA D.O.O.
OIB: {oib}

Račun br. 001/2026
Datum računa: 01.02.2026

Osnovica 25%:     1.000,00 EUR
PDV 25%:            300,00 EUR

Ukupno:           1.300,00 EUR
IBAN: HR1111222233334444555
        """
        result = self.ext.extract_from_text(text)
        # PDV 25% od 1000 = 250, ali račun kaže 300 → cross-validacija fail
        assert result["cross_validation_ok"] is False
        assert any("Cross-validacija" in w for w in result["warnings"])


class TestEracunXML:
    """eRačun XML parsing — treba dati 100% accuracy."""

    def test_basic_ubl_invoice(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        ext = InvoiceExtractor()

        xml = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>R1-001/2026</cbc:ID>
    <cbc:IssueDate>2026-02-15</cbc:IssueDate>
    <cbc:DueDate>2026-03-15</cbc:DueDate>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName><cbc:Name>Firma Test d.o.o.</cbc:Name></cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>HR12345678903</cbc:CompanyID>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:TaxTotal>
        <cbc:TaxAmount>250.00</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount>1000.00</cbc:TaxableAmount>
            <cbc:TaxAmount>250.00</cbc:TaxAmount>
            <cac:TaxCategory><cbc:Percent>25</cbc:Percent></cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:PayableAmount>1250.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""

        # Write to temp file
        tmpdir = tempfile.mkdtemp()
        fp = os.path.join(tmpdir, "eracun.xml")
        with open(fp, "w") as f:
            f.write(xml)

        result = ext.extract(fp)
        assert result["confidence"] == 1.0
        assert result["oib"] == "12345678903"
        assert result["ukupno"] == 1250.00
        assert result["pdv_ukupno"] == 250.00
        assert result["datum"] == "2026-02-15"
        assert result["source"] == "eracun_xml"


class TestOIBNotFromIBAN:
    """OIB ne smije biti izvučen iz IBAN-a."""

    def test_oib_not_from_iban(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        ext = InvoiceExtractor()

        # IBAN sadrži 19 znamenki, neka od 11-char substring-ova bi mogla
        # proći OIB regex — ali ne smije
        text = """
IBAN: HR1234567890123456789
Ukupno: 500,00 EUR
        """
        result = ext.extract_from_text(text)
        # OIB ne smije biti "12345678901" (dio IBAN-a)
        assert result["iban"] == "HR1234567890123456789"
        # Nema validnog OIB-a u tekstu
        assert result["oib_valid"] is False or result["oib"] == ""


class TestConfidenceBreakdown:
    """Confidence breakdown — ponderirani score."""

    def _make_valid_oib(self, first10="1234567890"):
        a = 10
        for d in first10:
            a = (a + int(d)) % 10
            if a == 0: a = 10
            a = (a * 2) % 11
        ctrl = 11 - a
        if ctrl == 10: ctrl = 0
        return first10 + str(ctrl)

    def test_full_invoice_high_confidence(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        oib = self._make_valid_oib()
        text = f"""
FIRMA TEST D.O.O.
OIB: {oib}
Račun br. 001/2026
Datum računa: 15.02.2026
PDV 25%: 250,00
Ukupno: 1.250,00
IBAN: HR1234567890123456789
        """
        result = ext.extract_from_text(text)
        bd = result["confidence_breakdown"]
        assert bd["oib"] == 1.0
        assert bd["ukupno"] == 1.0
        assert bd["datum"] == 1.0
        assert bd["iban"] == 1.0
        assert result["confidence"] >= 0.9

    def test_missing_fields_low_confidence(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        text = "Neki random tekst bez podataka računa"
        result = ext.extract_from_text(text)
        assert result["confidence"] < 0.3


class TestGetStats:
    """Statistike extractora."""

    def test_stats(self):
        from nyx_light.modules.invoice_ocr.extractor import InvoiceExtractor
        ext = InvoiceExtractor()
        ext.extract_from_text("Ukupno: 100,00")
        ext.extract_from_text("Ukupno: 200,00")
        stats = ext.get_stats()
        assert stats["extracted"] == 2
        assert stats["avg_confidence"] > 0
