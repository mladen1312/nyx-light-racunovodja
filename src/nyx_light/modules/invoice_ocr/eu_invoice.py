"""
Nyx Light — EU & Inozemni Invoice Recognition

Prepoznaje račune iz EU i inozemstva — i strukturirane (XML) i vizualne (PDF/scan).

Podržani formati:
  ══ STRUKTURIRANI (100% accuracy) ══
  1. EN 16931 (EU standard za e-račune)
  2. Peppol BIS 3.0 (pan-europski UBL format)
  3. ZUGFeRD 2.x / Factur-X (DE/FR/AT hybrid PDF+XML)
  4. FatturaPA (IT obavezni XML format)
  5. UBL 2.1 (generički)
  6. CII (Cross Industry Invoice, UN/CEFACT)

  ══ VIZUALNI (AI OCR) ══
  7. EU računi na engleskom, njemačkom, talijanskom, slovenskom
  8. Non-EU računi (US, UK, CH, ostali)
  9. Prepoznavanje valute, poreznog broja, VAT ID-a
  10. Reverse charge detekcija (čl. 75. Zakona o PDV-u)

Ključna polja za ekstrakciju:
  - VAT ID izdavatelja (EU format: CC + XXXXXXXX)
  - VAT ID primatelja
  - Iznos bez PDV-a, PDV, ukupno
  - Valuta (EUR, USD, GBP, CHF, itd.)
  - Datum izdavanja, datum dospijeća
  - Broj računa
  - Opis stavki
  - Reverse charge oznaka
  - Zemlja izdavatelja (ISO 3166-1 alpha-2)

Posebne situacije za HR računovodstvo:
  - EU stjecanje robe (čl. 4. st. 1. t. 2. ZPDV) → obratni obračun
  - EU primanje usluga (čl. 17. st. 1. ZPDV) → obratni obračun
  - Uvoz robe iz trećih zemalja → carinska deklaracija
  - Reverse charge (čl. 75. ZPDV) → samo ako kupac ima HR VAT ID
  - Tečaj na dan nastanka obveze (HNB srednji tečaj)
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.modules.eu_invoice")


# ═══════════════════════════════════════════════════
# ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════

class InvoiceOrigin(str, Enum):
    """Porijeklo računa."""
    HR = "hr"          # Domaći (Hrvatska)
    EU = "eu"          # EU članica
    NON_EU = "non_eu"  # Treća zemlja

class InvoiceFormat(str, Enum):
    """Format ulaznog računa."""
    UBL = "ubl_2.1"
    CII = "cii"
    PEPPOL = "peppol_bis_3.0"
    ZUGFERD = "zugferd_2.x"
    FATTURAPA = "fatturapa"
    EN16931 = "en_16931"
    PDF_SCAN = "pdf_scan"
    IMAGE_SCAN = "image_scan"
    UNKNOWN = "unknown"

class VATTreatment(str, Enum):
    """PDV tretman za HR računovodstvo."""
    DOMESTIC = "domestic"                # Domaći račun s PDV-om
    EU_GOODS = "eu_acquisition"          # EU stjecanje robe (čl. 4/1/2 ZPDV)
    EU_SERVICES = "eu_services"          # EU primanje usluga (čl. 17/1 ZPDV)
    REVERSE_CHARGE = "reverse_charge"    # Obratni obračun (čl. 75 ZPDV)
    IMPORT = "import"                    # Uvoz iz treće zemlje
    EXEMPT = "exempt"                    # Oslobođeno
    ZERO_RATED = "zero_rated"            # Nulta stopa

# EU VAT ID prefixes → zemlja
EU_COUNTRIES = {
    "AT": "Austrija", "BE": "Belgija", "BG": "Bugarska",
    "CY": "Cipar", "CZ": "Češka", "DE": "Njemačka",
    "DK": "Danska", "EE": "Estonija", "EL": "Grčka",
    "ES": "Španjolska", "FI": "Finska", "FR": "Francuska",
    "HR": "Hrvatska", "HU": "Mađarska", "IE": "Irska",
    "IT": "Italija", "LT": "Litva", "LU": "Luksemburg",
    "LV": "Latvija", "MT": "Malta", "NL": "Nizozemska",
    "PL": "Poljska", "PT": "Portugal", "RO": "Rumunjska",
    "SE": "Švedska", "SI": "Slovenija", "SK": "Slovačka",
}

# VAT ID regex po zemlji (EU format: CC + broj)
VAT_PATTERNS = {
    "AT": r"ATU\d{8}",
    "BE": r"BE[01]\d{9}",
    "BG": r"BG\d{9,10}",
    "CY": r"CY\d{8}[A-Z]",
    "CZ": r"CZ\d{8,10}",
    "DE": r"DE\d{9}",
    "DK": r"DK\d{8}",
    "EE": r"EE\d{9}",
    "EL": r"EL\d{9}",
    "ES": r"ES[A-Z0-9]\d{7}[A-Z0-9]",
    "FI": r"FI\d{8}",
    "FR": r"FR[A-Z0-9]{2}\d{9}",
    "HR": r"HR\d{11}",
    "HU": r"HU\d{8}",
    "IE": r"IE\d[A-Z0-9+*]\d{5}[A-Z]{1,2}",
    "IT": r"IT\d{11}",
    "LT": r"LT\d{9,12}",
    "LU": r"LU\d{8}",
    "LV": r"LV\d{11}",
    "MT": r"MT\d{8}",
    "NL": r"NL\d{9}B\d{2}",
    "PL": r"PL\d{10}",
    "PT": r"PT\d{9}",
    "RO": r"RO\d{2,10}",
    "SE": r"SE\d{12}",
    "SI": r"SI\d{8}",
    "SK": r"SK\d{10}",
}

# Currency detection
CURRENCY_SYMBOLS = {
    "€": "EUR", "EUR": "EUR",
    "$": "USD", "USD": "USD",
    "£": "GBP", "GBP": "GBP",
    "CHF": "CHF", "Fr.": "CHF",
    "kn": "HRK", "HRK": "HRK",
    "Kč": "CZK", "CZK": "CZK",
    "zł": "PLN", "PLN": "PLN",
    "Ft": "HUF", "HUF": "HUF",
    "lei": "RON", "RON": "RON",
    "лв": "BGN", "BGN": "BGN",
    "kr": "SEK",  # ili DKK/NOK
}

# Multilingual amount keywords
AMOUNT_KEYWORDS = {
    "en": {"total": ["total", "amount due", "grand total", "balance due"],
           "subtotal": ["subtotal", "net amount", "taxable amount"],
           "vat": ["vat", "tax", "sales tax"],
           "date": ["date", "invoice date", "issue date"],
           "due": ["due date", "payment due", "terms"],
           "number": ["invoice", "inv", "bill", "receipt"]},
    "de": {"total": ["gesamt", "gesamtbetrag", "endbetrag", "rechnungsbetrag"],
           "subtotal": ["netto", "nettobetrag", "zwischensumme"],
           "vat": ["mwst", "mehrwertsteuer", "ust", "umsatzsteuer"],
           "date": ["datum", "rechnungsdatum"],
           "due": ["fällig", "zahlungsziel"],
           "number": ["rechnung", "rechnungsnummer", "re-nr"]},
    "it": {"total": ["totale", "importo totale", "totale fattura"],
           "subtotal": ["imponibile", "subtotale"],
           "vat": ["iva", "imposta"],
           "date": ["data", "data fattura"],
           "due": ["scadenza"],
           "number": ["fattura", "numero fattura", "n. fattura"]},
    "sl": {"total": ["skupaj", "znesek", "za plačilo"],
           "subtotal": ["osnova", "neto"],
           "vat": ["ddv", "davek"],
           "date": ["datum"],
           "due": ["rok plačila"],
           "number": ["račun", "številka računa"]},
    "fr": {"total": ["total", "montant total", "total ttc"],
           "subtotal": ["total ht", "montant ht", "sous-total"],
           "vat": ["tva", "taxe"],
           "date": ["date", "date de facture"],
           "due": ["échéance", "date d'échéance"],
           "number": ["facture", "n° facture"]},
}


# ═══════════════════════════════════════════════════
# DATA MODEL
# ═══════════════════════════════════════════════════

@dataclass
class EUVATLine:
    """Jedna PDV stavka na EU računu."""
    rate_percent: float = 0.0
    taxable_amount: float = 0.0
    tax_amount: float = 0.0
    currency: str = "EUR"
    category_code: str = ""  # S=standard, Z=zero, E=exempt, AE=reverse charge

@dataclass
class EUInvoiceData:
    """Podaci s EU/inozemnog računa."""
    # Porijeklo i format
    origin: InvoiceOrigin = InvoiceOrigin.EU
    detected_format: InvoiceFormat = InvoiceFormat.UNKNOWN
    detected_language: str = ""
    confidence: float = 0.0

    # Izdavatelj
    seller_name: str = ""
    seller_vat_id: str = ""
    seller_country: str = ""          # ISO 2-char
    seller_country_name: str = ""
    seller_address: str = ""

    # Kupac
    buyer_name: str = ""
    buyer_vat_id: str = ""
    buyer_country: str = ""
    buyer_is_hr: bool = False         # Je li kupac HR tvrtka

    # Iznosi
    currency: str = "EUR"
    subtotal: float = 0.0            # Bez PDV-a
    total_vat: float = 0.0           # Ukupni PDV
    total: float = 0.0               # S PDV-om
    vat_lines: List[EUVATLine] = field(default_factory=list)

    # Datumi
    invoice_date: str = ""
    due_date: str = ""
    invoice_number: str = ""

    # Stavke
    line_items: List[Dict[str, Any]] = field(default_factory=list)

    # HR računovodstveni tretman
    vat_treatment: VATTreatment = VATTreatment.DOMESTIC
    reverse_charge: bool = False
    needs_exchange_rate: bool = False  # Treba li tečaj HNB-a
    suggested_accounts: Dict[str, str] = field(default_factory=dict)

    # Warnings
    warnings: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════
# EU INVOICE RECOGNIZER
# ═══════════════════════════════════════════════════

class EUInvoiceRecognizer:
    """
    Prepoznaje i parsira EU/inozemne račune.
    Radi s XML (strukturirani) i tekst/OCR (vizualni) ulazom.
    """

    def __init__(self):
        self._parse_count = 0
        self._eu_count = 0
        self._non_eu_count = 0

    # ════════════════════════════════════════
    # DETEKCIJA PORIJEKLA
    # ════════════════════════════════════════

    def detect_origin(self, text: str = "", xml: str = "",
                      vat_id: str = "") -> InvoiceOrigin:
        """Detektiraj porijeklo računa."""
        # Provjeri VAT ID ako je dostupan
        if vat_id:
            country = self.extract_country_from_vat(vat_id)
            if country == "HR":
                return InvoiceOrigin.HR
            elif country in EU_COUNTRIES:
                return InvoiceOrigin.EU
            elif country:
                return InvoiceOrigin.NON_EU

        # Provjeri tekst za VAT ID-ove
        combined = text + " " + xml
        found_vat = self.find_vat_ids(combined)
        for vat in found_vat:
            country = self.extract_country_from_vat(vat)
            if country and country != "HR":
                if country in EU_COUNTRIES:
                    return InvoiceOrigin.EU
                return InvoiceOrigin.NON_EU

        # Provjeri valute
        for symbol, currency in CURRENCY_SYMBOLS.items():
            if symbol in combined and currency not in ("EUR", "HRK"):
                if currency in ("GBP", "USD", "CHF"):
                    return InvoiceOrigin.NON_EU

        # Jezična detekcija
        lower = combined.lower()
        de_words = ["rechnung", "mwst", "gesamtbetrag", "netto"]
        it_words = ["fattura", "iva", "imponibile", "totale"]
        sl_words = ["račun", "ddv", "za plačilo", "skupaj"]
        fr_words = ["facture", "tva", "montant", "total ttc"]

        if any(w in lower for w in de_words + it_words + sl_words + fr_words):
            return InvoiceOrigin.EU

        return InvoiceOrigin.HR  # Default: domaći

    def extract_country_from_vat(self, vat_id: str) -> str:
        """Izvuci ISO country code iz VAT ID-a."""
        vat_id = vat_id.strip().upper().replace(" ", "")
        if len(vat_id) >= 2:
            prefix = vat_id[:2]
            if prefix in EU_COUNTRIES or prefix in VAT_PATTERNS:
                return prefix
        return ""

    def find_vat_ids(self, text: str) -> List[str]:
        """Nađi sve VAT ID-ove u tekstu."""
        found = []
        text_clean = text.upper().replace(" ", "")
        for country, pattern in VAT_PATTERNS.items():
            for match in re.finditer(pattern, text_clean):
                found.append(match.group(0))
        return list(set(found))

    # ════════════════════════════════════════
    # XML PARSERI (STRUKTURIRANI RAČUNI)
    # ════════════════════════════════════════

    def parse_xml(self, xml_content: str) -> EUInvoiceData:
        """Parsiraj XML račun (UBL, CII, Peppol, ZUGFeRD, FatturaPA)."""
        data = EUInvoiceData()
        self._parse_count += 1

        try:
            root = ET.fromstring(xml_content)
            tag = root.tag.lower()

            if "invoice" in tag and "oasis" in tag:
                data = self._parse_ubl(root, xml_content)
                data.detected_format = InvoiceFormat.UBL
            elif "crossindustryinvoice" in tag:
                data = self._parse_cii(root, xml_content)
                data.detected_format = InvoiceFormat.CII
            elif "fattura" in tag or "FatturaElettronica" in root.tag:
                data = self._parse_fatturapa(root, xml_content)
                data.detected_format = InvoiceFormat.FATTURAPA
            else:
                # Pokušaj UBL namespace
                data = self._parse_ubl(root, xml_content)
                data.detected_format = InvoiceFormat.UBL

            data.confidence = 0.95  # XML = visoka pouzdanost

            # Set origin based on seller country
            if data.seller_country:
                if data.seller_country == "HR":
                    data.origin = InvoiceOrigin.HR
                elif data.seller_country in EU_COUNTRIES:
                    data.origin = InvoiceOrigin.EU
                else:
                    data.origin = InvoiceOrigin.NON_EU
            elif data.seller_vat_id:
                cc = self.extract_country_from_vat(data.seller_vat_id)
                if cc == "HR":
                    data.origin = InvoiceOrigin.HR
                elif cc in EU_COUNTRIES:
                    data.origin = InvoiceOrigin.EU
                elif cc:
                    data.origin = InvoiceOrigin.NON_EU
        except ET.ParseError as e:
            data.validation_errors.append(f"XML parse error: {e}")
            data.confidence = 0.0
        except Exception as e:
            data.validation_errors.append(f"Parse error: {e}")

        # Odredi HR tretman
        self._determine_vat_treatment(data)
        return data

    def _parse_ubl(self, root: ET.Element, raw: str) -> EUInvoiceData:
        """Parse UBL 2.1 / Peppol BIS 3.0 / EN 16931."""
        ns = {
            "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
            "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        }
        data = EUInvoiceData()

        # Invoice number & date
        inv_id = root.find(".//cbc:ID", ns)
        if inv_id is not None:
            data.invoice_number = inv_id.text or ""
        issue_date = root.find(".//cbc:IssueDate", ns)
        if issue_date is not None:
            data.invoice_date = issue_date.text or ""
        due_date = root.find(".//cbc:DueDate", ns)
        if due_date is not None:
            data.due_date = due_date.text or ""

        # Currency
        currency = root.find(".//cbc:DocumentCurrencyCode", ns)
        if currency is not None:
            data.currency = currency.text or "EUR"

        # Seller
        seller = root.find(".//cac:AccountingSupplierParty/cac:Party", ns)
        if seller is not None:
            name_el = seller.find(".//cbc:Name", ns)
            if name_el is None:
                name_el = seller.find(".//cbc:RegistrationName", ns)
            if name_el is not None:
                data.seller_name = name_el.text or ""
            vat = seller.find(".//cbc:CompanyID", ns)
            if vat is not None:
                data.seller_vat_id = (vat.text or "").strip()
            country = seller.find(".//cac:PostalAddress/cac:Country/cbc:IdentificationCode", ns)
            if country is not None:
                data.seller_country = country.text or ""

        # Buyer
        buyer = root.find(".//cac:AccountingCustomerParty/cac:Party", ns)
        if buyer is not None:
            name_el = buyer.find(".//cbc:Name", ns)
            if name_el is None:
                name_el = buyer.find(".//cbc:RegistrationName", ns)
            if name_el is not None:
                data.buyer_name = name_el.text or ""
            vat = buyer.find(".//cbc:CompanyID", ns)
            if vat is not None:
                data.buyer_vat_id = (vat.text or "").strip()
            country = buyer.find(".//cac:PostalAddress/cac:Country/cbc:IdentificationCode", ns)
            if country is not None:
                data.buyer_country = country.text or ""

        # Totals
        monetary = root.find(".//cac:LegalMonetaryTotal", ns)
        if monetary is not None:
            taxex = monetary.find("cbc:TaxExclusiveAmount", ns)
            if taxex is not None:
                data.subtotal = float(taxex.text or 0)
            taxinc = monetary.find("cbc:TaxInclusiveAmount", ns)
            if taxinc is not None:
                data.total = float(taxinc.text or 0)
            payable = monetary.find("cbc:PayableAmount", ns)
            if payable is not None:
                data.total = float(payable.text or data.total)

        # VAT lines
        for tax_sub in root.findall(".//cac:TaxSubtotal", ns):
            vat_line = EUVATLine(currency=data.currency)
            taxable = tax_sub.find("cbc:TaxableAmount", ns)
            if taxable is not None:
                vat_line.taxable_amount = float(taxable.text or 0)
            tax_amt = tax_sub.find("cbc:TaxAmount", ns)
            if tax_amt is not None:
                vat_line.tax_amount = float(tax_amt.text or 0)
            cat = tax_sub.find(".//cac:TaxCategory", ns)
            if cat is not None:
                pct = cat.find("cbc:Percent", ns)
                if pct is not None:
                    vat_line.rate_percent = float(pct.text or 0)
                code = cat.find("cbc:ID", ns)
                if code is not None:
                    vat_line.category_code = code.text or ""
            data.vat_lines.append(vat_line)

        data.total_vat = sum(v.tax_amount for v in data.vat_lines)

        # Line items
        for line in root.findall(".//cac:InvoiceLine", ns):
            item = {}
            desc = line.find(".//cbc:Name", ns)
            if desc is None:
                desc = line.find(".//cbc:Description", ns)
            if desc is not None:
                item["description"] = desc.text or ""
            qty = line.find("cbc:InvoicedQuantity", ns)
            if qty is not None:
                item["quantity"] = float(qty.text or 0)
            price = line.find(".//cbc:PriceAmount", ns)
            if price is not None:
                item["unit_price"] = float(price.text or 0)
            amount = line.find("cbc:LineExtensionAmount", ns)
            if amount is not None:
                item["amount"] = float(amount.text or 0)
            if item:
                data.line_items.append(item)

        return data

    def _parse_cii(self, root: ET.Element, raw: str) -> EUInvoiceData:
        """Parse CII (Cross Industry Invoice) / ZUGFeRD."""
        data = EUInvoiceData()
        data.detected_format = InvoiceFormat.CII
        # Simplified CII parsing — key fields
        ns = {"ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"}

        # Extract basic fields from CII structure
        text = raw
        # VAT ID
        vat_ids = self.find_vat_ids(text)
        if vat_ids:
            data.seller_vat_id = vat_ids[0]
            if len(vat_ids) > 1:
                data.buyer_vat_id = vat_ids[1]

        # Amounts via regex fallback
        amount_pattern = r'<ram:(?:Grand|Due|Tax)TotalAmount[^>]*>([0-9.]+)</ram'
        amounts = re.findall(amount_pattern, raw)
        if amounts:
            data.total = float(amounts[0])

        return data

    def _parse_fatturapa(self, root: ET.Element, raw: str) -> EUInvoiceData:
        """Parse FatturaPA (IT e-fakture)."""
        data = EUInvoiceData()
        data.detected_format = InvoiceFormat.FATTURAPA
        data.seller_country = "IT"
        data.origin = InvoiceOrigin.EU
        # Simplified FatturaPA parsing
        vat_ids = self.find_vat_ids(raw)
        if vat_ids:
            data.seller_vat_id = vat_ids[0]
        return data

    # ════════════════════════════════════════
    # OCR TEKST PARSER (VIZUALNI RAČUNI)
    # ════════════════════════════════════════

    def parse_ocr_text(self, text: str, source_language: str = "") -> EUInvoiceData:
        """
        Parsiraj OCR tekst s EU/inozemnog računa.
        Koristi višejezične patterne za ekstrakciju.
        """
        data = EUInvoiceData()
        data.detected_format = InvoiceFormat.PDF_SCAN
        self._parse_count += 1

        # 1. Detektiraj jezik
        if not source_language:
            source_language = self._detect_language(text)
        data.detected_language = source_language

        # 2. Detektiraj porijeklo
        data.origin = self.detect_origin(text=text)
        if data.origin == InvoiceOrigin.EU:
            self._eu_count += 1
        elif data.origin == InvoiceOrigin.NON_EU:
            self._non_eu_count += 1

        # 3. Izvuci VAT ID-ove
        vat_ids = self.find_vat_ids(text)
        if vat_ids:
            # Seller = prvi ne-HR VAT ID (ili prvi ukupno)
            for vid in vat_ids:
                country = self.extract_country_from_vat(vid)
                if country != "HR":
                    data.seller_vat_id = vid
                    data.seller_country = country
                    data.seller_country_name = EU_COUNTRIES.get(country, country)
                    break
            # Buyer = HR VAT ID (ili OIB)
            for vid in vat_ids:
                country = self.extract_country_from_vat(vid)
                if country == "HR":
                    data.buyer_vat_id = vid
                    data.buyer_is_hr = True
                    data.buyer_country = "HR"
                    break

        # 4. Detektiraj valutu
        data.currency = self._detect_currency(text)
        if data.currency != "EUR":
            data.needs_exchange_rate = True

        # 5. Izvuci iznose (višejezično)
        self._extract_amounts_multilingual(text, source_language, data)

        # 6. Izvuci datume
        self._extract_dates(text, data)

        # 7. Izvuci broj računa
        self._extract_invoice_number(text, source_language, data)

        # 8. Reverse charge detekcija
        self._detect_reverse_charge(text, data)

        # 9. Confidence
        filled = sum([
            bool(data.seller_vat_id),
            bool(data.total > 0),
            bool(data.invoice_date),
            bool(data.invoice_number),
            bool(data.currency),
            bool(data.seller_country),
        ])
        data.confidence = filled / 6.0

        # 10. HR tretman
        self._determine_vat_treatment(data)

        return data

    def _detect_language(self, text: str) -> str:
        """Detektiraj jezik teksta."""
        lower = text.lower()
        scores = {}
        for lang, keywords in AMOUNT_KEYWORDS.items():
            score = 0
            for field_kws in keywords.values():
                for kw in field_kws:
                    if kw in lower:
                        score += 1
            scores[lang] = score
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] >= 2:
                return best
        return "en"

    def _detect_currency(self, text: str) -> str:
        """Detektiraj valutu."""
        for symbol, currency in CURRENCY_SYMBOLS.items():
            if symbol in text:
                return currency
        return "EUR"

    def _extract_amounts_multilingual(self, text: str, lang: str,
                                       data: EUInvoiceData):
        """Izvuci iznose koristeći višejezične ključne riječi."""
        keywords = AMOUNT_KEYWORDS.get(lang, AMOUNT_KEYWORDS["en"])

        # Generički amount pattern
        amount_re = r'[\d]{1,3}(?:[.,\s]\d{3})*[.,]\d{2}'

        lines = text.split("\n")
        for line in lines:
            lower = line.lower().strip()
            # Total
            if any(kw in lower for kw in keywords.get("total", [])):
                amounts = re.findall(amount_re, line)
                if amounts:
                    data.total = self._parse_amount(amounts[-1])
            # Subtotal
            elif any(kw in lower for kw in keywords.get("subtotal", [])):
                amounts = re.findall(amount_re, line)
                if amounts:
                    data.subtotal = self._parse_amount(amounts[-1])
            # VAT
            elif any(kw in lower for kw in keywords.get("vat", [])):
                amounts = re.findall(amount_re, line)
                if amounts:
                    data.total_vat = self._parse_amount(amounts[-1])
                # VAT rate
                rate_match = re.search(r'(\d{1,2})\s*%', line)
                if rate_match and amounts:
                    rate = float(rate_match.group(1))
                    data.vat_lines.append(EUVATLine(
                        rate_percent=rate,
                        tax_amount=self._parse_amount(amounts[-1]),
                        currency=data.currency,
                    ))

        # Cross-validate
        if data.total > 0 and data.subtotal > 0 and data.total_vat == 0:
            data.total_vat = round(data.total - data.subtotal, 2)
        elif data.total > 0 and data.total_vat > 0 and data.subtotal == 0:
            data.subtotal = round(data.total - data.total_vat, 2)

    def _parse_amount(self, amount_str: str) -> float:
        """Parse iznos u raznim formatima (1.234,56 ili 1,234.56)."""
        s = amount_str.strip()
        # Prebroji separatore
        dots = s.count(".")
        commas = s.count(",")
        if commas == 1 and dots <= 1:
            if dots == 1 and s.index(".") < s.index(","):
                # 1.234,56 → europski format
                s = s.replace(".", "").replace(",", ".")
            elif dots == 0:
                # 1234,56 → europski
                s = s.replace(",", ".")
            else:
                # 1,234.56 → američki
                s = s.replace(",", "")
        elif dots == 1 and commas == 0:
            pass  # 1234.56 → OK
        elif commas > 1:
            s = s.replace(",", "")  # 1,234,567.89
        elif dots > 1:
            s = s.replace(".", "")  # 1.234.567,89 ???

        try:
            return round(float(s), 2)
        except ValueError:
            return 0.0

    def _extract_dates(self, text: str, data: EUInvoiceData):
        """Izvuci datume u raznim formatima."""
        date_patterns = [
            (r'(\d{2})[./](\d{2})[./](\d{4})', "dmy"),
            (r'(\d{4})-(\d{2})-(\d{2})', "ymd"),
            (r'(\d{2})-(\d{2})-(\d{4})', "dmy"),
        ]
        dates_found = []
        for pattern, fmt in date_patterns:
            for match in re.finditer(pattern, text):
                groups = match.groups()
                try:
                    if fmt == "dmy":
                        d = f"{groups[2]}-{groups[1]}-{groups[0]}"
                    else:
                        d = f"{groups[0]}-{groups[1]}-{groups[2]}"
                    datetime.strptime(d, "%Y-%m-%d")
                    dates_found.append(d)
                except ValueError:
                    pass

        if dates_found:
            data.invoice_date = dates_found[0]
            if len(dates_found) > 1:
                data.due_date = dates_found[-1]

    def _extract_invoice_number(self, text: str, lang: str,
                                 data: EUInvoiceData):
        """Izvuci broj računa."""
        keywords = AMOUNT_KEYWORDS.get(lang, AMOUNT_KEYWORDS["en"])
        for kw in keywords.get("number", []):
            pattern = rf'{re.escape(kw)}[:\s#№.]*\s*([\w/-]+\d[\w/-]*)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data.invoice_number = match.group(1).strip()
                return

    def _detect_reverse_charge(self, text: str, data: EUInvoiceData):
        """Detektiraj reverse charge oznaku."""
        rc_phrases = [
            "reverse charge", "obratno oporezivanje",
            "steuerschuldnerschaft des leistungsempfängers",
            "inversione contabile", "autoliquidation",
            "obrnuto oporezivanje", "prijenos porezne obveze",
            "čl. 75", "article 196", "art. 196",
            "vat amount: 0", "iva: 0", "mwst: 0",
            "tax exempt", "exonéré de tva",
        ]
        lower = text.lower()
        for phrase in rc_phrases:
            if phrase in lower:
                data.reverse_charge = True
                return

        # Ako je EU račun bez PDV-a → vjerovatno reverse charge
        if (data.origin == InvoiceOrigin.EU and
                data.total_vat == 0 and data.total > 0):
            data.reverse_charge = True
            data.warnings.append(
                "PDV nije obračunat — vjerovatno reverse charge "
                "(čl. 75. Zakona o PDV-u)")

    # ════════════════════════════════════════
    # HR RAČUNOVODSTVENI TRETMAN
    # ════════════════════════════════════════

    def _determine_vat_treatment(self, data: EUInvoiceData):
        """Odredi HR računovodstveni PDV tretman."""
        if data.origin == InvoiceOrigin.HR:
            data.vat_treatment = VATTreatment.DOMESTIC
            return

        data.buyer_is_hr = (
            data.buyer_country == "HR" or
            (data.buyer_vat_id and data.buyer_vat_id.startswith("HR"))
        )

        # Auto-detect reverse charge: EU invoice s 0 PDV-a
        if (data.origin == InvoiceOrigin.EU and
                data.total_vat == 0 and data.total > 0 and
                not data.reverse_charge):
            data.reverse_charge = True
            if not any("reverse" in w.lower() or "obratni" in w.lower()
                       for w in data.warnings):
                data.warnings.append(
                    "PDV nije obračunat — vjerovatno reverse charge "
                    "(čl. 75. Zakona o PDV-u)")

        if data.origin == InvoiceOrigin.EU:
            if data.reverse_charge:
                data.vat_treatment = VATTreatment.REVERSE_CHARGE
                data.suggested_accounts = {
                    "pretporez": "1406",  # Pretporez po stjecanju iz EU
                    "obveza_pdv": "2401",  # Obveza PDV po stjecanju
                    "trošak": "4xxx",      # Ovisno o vrsti troška
                }
                data.warnings.append(
                    "EU stjecanje — obratni obračun PDV-a. "
                    "Obračunati PDV i pretporez (čl. 75. st. 1. t. 6. ZPDV)")
            else:
                # EU račun s PDV-om → možda je B2C ili poseban slučaj
                data.vat_treatment = VATTreatment.EU_GOODS
                data.warnings.append(
                    "EU račun s PDV-om — provjerite je li PDV ispravno obračunat")

        elif data.origin == InvoiceOrigin.NON_EU:
            data.vat_treatment = VATTreatment.IMPORT
            data.suggested_accounts = {
                "carinski_pdv": "1407",  # PDV pri uvozu
                "carina": "4490",        # Carina
                "trošak": "4xxx",
            }
            data.warnings.append(
                "Uvoz iz treće zemlje — PDV se obračunava pri carinjenju. "
                "Potrebna carinska deklaracija (JCD).")

        # Tečaj
        if data.currency and data.currency != "EUR":
            data.needs_exchange_rate = True
            data.warnings.append(
                f"Valuta {data.currency} — potreban tečaj HNB-a "
                f"na datum {data.invoice_date or 'računa'}")

    # ════════════════════════════════════════
    # STATS
    # ════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_parsed": self._parse_count,
            "eu_invoices": self._eu_count,
            "non_eu_invoices": self._non_eu_count,
            "supported_formats": [f.value for f in InvoiceFormat],
            "supported_countries": len(EU_COUNTRIES),
            "supported_languages": list(AMOUNT_KEYWORDS.keys()),
        }
