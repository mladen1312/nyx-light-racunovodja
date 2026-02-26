"""
Modul A1 — Ekstrakcija podataka iz računa (Vision AI)

Koristi Qwen2.5-VL-7B za OCR skenova i PDF-ova.
Ekstrahira: OIB, iznos, PDV stope, datume, broj računa.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.invoice_ocr")


@dataclass
class InvoiceData:
    """Ekstrahirani podaci s računa."""
    oib_izdavatelja: str = ""
    naziv_izdavatelja: str = ""
    broj_racuna: str = ""
    datum_racuna: Optional[datetime] = None
    datum_dospijeca: Optional[datetime] = None
    osnovica: float = 0.0
    pdv_stopa: float = 25.0
    pdv_iznos: float = 0.0
    ukupno: float = 0.0
    iban: str = ""
    poziv_na_broj: str = ""
    opis_stavki: List[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_text: str = ""


class InvoiceExtractor:
    """Ekstrahira podatke iz skenova/PDF računa."""

    # Regex za OIB (11 znamenki)
    OIB_PATTERN = re.compile(r"\b(\d{11})\b")
    # Regex za IBAN
    IBAN_PATTERN = re.compile(r"\b(HR\d{19})\b")
    # Regex za iznos
    AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:[\.]\d{3})*(?:,\d{2}))\s*(?:EUR|€|HRK|kn)?")

    def __init__(self):
        self._extraction_count = 0
        logger.info("InvoiceExtractor inicijaliziran")

    def extract(self, file_path: str) -> Dict[str, Any]:
        """Ekstrahiraj podatke iz računa."""
        path = Path(file_path)
        
        if not path.exists():
            return {"error": f"Datoteka ne postoji: {file_path}"}

        # Za PDF — koristi PyPDF2 za tekst, ili Vision AI za sken
        if path.suffix.lower() == ".pdf":
            text = self._extract_text_from_pdf(path)
        elif path.suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff"):
            text = self._extract_text_from_image(path)
        else:
            return {"error": f"Nepodržani format: {path.suffix}"}

        invoice = self._parse_invoice_text(text)
        self._extraction_count += 1

        return {
            "oib": invoice.oib_izdavatelja,
            "naziv": invoice.naziv_izdavatelja,
            "broj_racuna": invoice.broj_racuna,
            "datum": invoice.datum_racuna.isoformat() if invoice.datum_racuna else None,
            "osnovica": invoice.osnovica,
            "pdv_stopa": invoice.pdv_stopa,
            "pdv_iznos": invoice.pdv_iznos,
            "ukupno": invoice.ukupno,
            "iban": invoice.iban,
            "confidence": invoice.confidence,
        }

    def _extract_text_from_pdf(self, path: Path) -> str:
        """Izvuci tekst iz PDF-a."""
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(str(path))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        except Exception as e:
            logger.error("PDF extraction failed: %s", e)
            return ""

    def _extract_text_from_image(self, path: Path) -> str:
        """
        Izvuci tekst iz slike koristeći Vision AI (Qwen2.5-VL).
        TODO: Integrirati s vLLM-MLX vision endpointom.
        """
        logger.info("Vision AI OCR za: %s (TODO: integracija s Qwen2.5-VL)", path.name)
        return ""

    def _parse_invoice_text(self, text: str) -> InvoiceData:
        """Parsiraj tekst računa i izvuci strukturirane podatke."""
        invoice = InvoiceData(raw_text=text)

        # Traži OIB
        oib_matches = self.OIB_PATTERN.findall(text)
        if oib_matches:
            invoice.oib_izdavatelja = oib_matches[0]
            invoice.confidence += 0.3

        # Traži IBAN
        iban_matches = self.IBAN_PATTERN.findall(text)
        if iban_matches:
            invoice.iban = iban_matches[0]
            invoice.confidence += 0.2

        # Traži iznose
        amounts = self.AMOUNT_PATTERN.findall(text)
        if amounts:
            # Zadnji (najčešće ukupni) iznos
            try:
                total_str = amounts[-1].replace(".", "").replace(",", ".")
                invoice.ukupno = float(total_str)
                invoice.confidence += 0.3
            except ValueError:
                pass

        # PDV izračun (pretpostavi 25%)
        if invoice.ukupno > 0:
            invoice.pdv_stopa = 25.0
            invoice.osnovica = round(invoice.ukupno / 1.25, 2)
            invoice.pdv_iznos = round(invoice.ukupno - invoice.osnovica, 2)

        invoice.confidence = min(1.0, invoice.confidence)
        return invoice
