"""
Nyx Light — Parseri za sekundarne ERP sustave klijenata

e-Računi (e-racuni.com) — 3 klijenta
Pantheon ERP — 3 klijenta

Ovi parseri čitaju export iz klijentskih programa i pretvaraju
ih u standardni BookingProposal format za uvoz u CPP/Synesis.
"""

import csv
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.external_parsers")


class ERacuniParser:
    """
    Parser za e-Računi (e-racuni.com) export.
    
    e-Računi koristi UBL 2.1 XML format za e-fakture.
    Podržava i CSV export iz platforme.
    """

    def __init__(self):
        self._parse_count = 0

    def parse_xml(self, xml_content: str) -> List[Dict[str, Any]]:
        """Parsiraj e-Računi UBL XML."""
        invoices = []
        try:
            root = ET.fromstring(xml_content)
            # UBL namespace
            ns = {
                "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
                "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
            }

            invoice = {
                "source": "eRacuni",
                "broj_racuna": self._find_text(root, ".//cbc:ID", ns),
                "datum": self._find_text(root, ".//cbc:IssueDate", ns),
                "rok_placanja": self._find_text(root, ".//cbc:DueDate", ns),
                "valuta": self._find_text(root, ".//cbc:DocumentCurrencyCode", ns) or "EUR",
            }

            # Dobavljač
            supplier = root.find(".//cac:AccountingSupplierParty", ns)
            if supplier is not None:
                invoice["dobavljac"] = self._find_text(
                    supplier, ".//cbc:RegistrationName", ns
                ) or self._find_text(supplier, ".//cbc:Name", ns) or ""
                invoice["oib_dobavljaca"] = self._find_text(
                    supplier, ".//cbc:CompanyID", ns) or ""

            # Kupac
            customer = root.find(".//cac:AccountingCustomerParty", ns)
            if customer is not None:
                invoice["kupac"] = self._find_text(
                    customer, ".//cbc:RegistrationName", ns) or ""
                invoice["oib_kupca"] = self._find_text(
                    customer, ".//cbc:CompanyID", ns) or ""

            # Iznosi
            monetary = root.find(".//cac:LegalMonetaryTotal", ns)
            if monetary is not None:
                invoice["osnovica"] = self._parse_float(
                    self._find_text(monetary, "cbc:TaxExclusiveAmount", ns))
                invoice["ukupno"] = self._parse_float(
                    self._find_text(monetary, "cbc:PayableAmount", ns))

            # PDV
            tax_total = root.find(".//cac:TaxTotal", ns)
            if tax_total is not None:
                invoice["pdv_iznos"] = self._parse_float(
                    self._find_text(tax_total, "cbc:TaxAmount", ns))
                subtotal = tax_total.find(".//cac:TaxSubtotal", ns)
                if subtotal is not None:
                    cat = subtotal.find(".//cac:TaxCategory", ns)
                    if cat is not None:
                        invoice["pdv_stopa"] = self._parse_float(
                            self._find_text(cat, "cbc:Percent", ns))

            # Stavke
            invoice["stavke"] = []
            for line in root.findall(".//cac:InvoiceLine", ns):
                stavka = {
                    "opis": self._find_text(line, ".//cbc:Name", ns) or
                            self._find_text(line, ".//cac:Item/cbc:Name", ns) or "",
                    "kolicina": self._parse_float(
                        self._find_text(line, "cbc:InvoicedQuantity", ns)),
                    "cijena": self._parse_float(
                        self._find_text(line, ".//cbc:PriceAmount", ns)),
                    "iznos": self._parse_float(
                        self._find_text(line, "cbc:LineExtensionAmount", ns)),
                }
                invoice["stavke"].append(stavka)

            invoices.append(invoice)
            self._parse_count += 1

        except ET.ParseError as e:
            logger.warning("e-Računi XML parse error: %s", e)
            return [{"error": str(e), "source": "eRacuni"}]

        return invoices

    def parse_csv(self, csv_content: str, delimiter: str = ",") -> List[Dict[str, Any]]:
        """Parsiraj e-Računi CSV export."""
        invoices = []
        reader = csv.DictReader(csv_content.strip().splitlines(), delimiter=delimiter)
        for row in reader:
            invoice = {
                "source": "eRacuni",
                "broj_racuna": row.get("Broj", row.get("InvoiceNumber", "")),
                "datum": row.get("Datum", row.get("IssueDate", "")),
                "dobavljac": row.get("Dobavljac", row.get("SupplierName", "")),
                "oib_dobavljaca": row.get("OIB", row.get("SupplierVAT", "")),
                "osnovica": self._parse_float(row.get("Osnovica", row.get("TaxBase", "0"))),
                "pdv_stopa": self._parse_float(row.get("PDVStopa", row.get("TaxRate", "25"))),
                "pdv_iznos": self._parse_float(row.get("PDVIznos", row.get("TaxAmount", "0"))),
                "ukupno": self._parse_float(row.get("Ukupno", row.get("TotalAmount", "0"))),
            }
            invoices.append(invoice)
            self._parse_count += 1

        return invoices

    def _find_text(self, element, path, ns=None):
        el = element.find(path, ns) if ns else element.find(path)
        return el.text if el is not None else ""

    def _parse_float(self, val):
        try:
            return round(float(val.replace(",", ".")), 2) if val else 0.0
        except (ValueError, AttributeError):
            return 0.0

    def get_stats(self):
        return {"eracuni_parsed": self._parse_count}


class PantheonParser:
    """
    Parser za Pantheon ERP export.
    
    Pantheon koristi specifični CSV/TXT format za export knjiženja.
    """

    def __init__(self):
        self._parse_count = 0

    def parse_export(self, content: str, fmt: str = "csv") -> List[Dict[str, Any]]:
        """Parsiraj Pantheon export (CSV ili TXT)."""
        if fmt == "csv":
            return self._parse_csv(content)
        elif fmt == "txt":
            return self._parse_txt(content)
        return []

    def _parse_csv(self, content: str) -> List[Dict[str, Any]]:
        """Pantheon CSV export."""
        records = []
        delimiter = ";" if ";" in content.split("\n")[0] else ","
        reader = csv.DictReader(content.strip().splitlines(), delimiter=delimiter)

        for row in reader:
            record = {
                "source": "Pantheon",
                "document_type": row.get("TipDokumenta", row.get("DocType", "")),
                "broj_dokumenta": row.get("BrojDokumenta", row.get("DocNo", "")),
                "datum": row.get("Datum", row.get("Date", "")),
                "konto": row.get("Konto", row.get("Account", "")),
                "partner": row.get("Partner", row.get("PartnerName", "")),
                "oib": row.get("OIB", row.get("VATNo", "")),
                "opis": row.get("Opis", row.get("Description", "")),
                "duguje": self._parse_float(row.get("Duguje", row.get("Debit", "0"))),
                "potrazuje": self._parse_float(row.get("Potrazuje", row.get("Credit", "0"))),
            }
            records.append(record)
            self._parse_count += 1

        return records

    def _parse_txt(self, content: str) -> List[Dict[str, Any]]:
        """Pantheon TXT fixed-width export."""
        records = []
        for line in content.strip().split("\n"):
            if len(line) < 50 or line.startswith("#"):
                continue
            try:
                record = {
                    "source": "Pantheon",
                    "konto": line[0:6].strip(),
                    "datum": line[6:16].strip(),
                    "opis": line[16:56].strip(),
                    "duguje": self._parse_float(line[56:72].strip()),
                    "potrazuje": self._parse_float(line[72:88].strip()),
                    "oib": line[88:99].strip() if len(line) > 88 else "",
                }
                records.append(record)
                self._parse_count += 1
            except (IndexError, ValueError):
                continue

        return records

    def to_booking_proposals(
        self, records: List[Dict], client_id: str, erp_target: str = "CPP"
    ) -> List[Dict[str, Any]]:
        """
        Pretvori Pantheon zapise u format za BookingPipeline.
        Mapira Pantheon konte na CPP/Synesis kontni plan.
        """
        proposals = []
        for rec in records:
            iznos = rec.get("duguje", 0) or rec.get("potrazuje", 0)
            strana = "duguje" if rec.get("duguje", 0) > 0 else "potrazuje"

            proposals.append({
                "source": "Pantheon",
                "client_id": client_id,
                "erp_target": erp_target,
                "konto": rec.get("konto", ""),
                "strana": strana,
                "iznos": iznos,
                "opis": rec.get("opis", ""),
                "datum": rec.get("datum", ""),
                "oib": rec.get("oib", ""),
                "partner": rec.get("partner", ""),
                "requires_konto_mapping": True,  # Pantheon konte treba mapirati
            })

        return proposals

    def _parse_float(self, val):
        try:
            return round(float(str(val).replace(",", ".").replace(" ", "")), 2)
        except (ValueError, TypeError):
            return 0.0

    def get_stats(self):
        return {"pantheon_parsed": self._parse_count}
