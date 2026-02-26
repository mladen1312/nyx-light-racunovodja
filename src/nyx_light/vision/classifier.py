"""
Nyx Light — Document Classifier

Automatska klasifikacija dokumenata prema tipu za routing u odgovarajući modul.
Koristi kombinirani pristup:
  1. Heuristika (filename, extension, keywords) — brzo
  2. Vision AI (Qwen2.5-VL) — za nejasne slučajeve
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .pipeline import DocumentType

logger = logging.getLogger("nyx_light.vision.classifier")

# Heuristička pravila za klasifikaciju na temelju naziva datoteke
FILENAME_PATTERNS: List[Tuple[re.Pattern, DocumentType]] = [
    # Bankovni izvodi
    (re.compile(r"(?:mt940|mt\s*940)", re.I), DocumentType.BANKOVNI_IZVOD),
    (re.compile(r"(?:izvod|bank.*statement|izvadak)", re.I), DocumentType.BANKOVNI_IZVOD),
    (re.compile(r"(?:erste|zaba|pbz|rba|otp|hpb|sber).*(?:izvod|csv|txt)", re.I), DocumentType.BANKOVNI_IZVOD),

    # Računi
    (re.compile(r"(?:racun|faktura|invoice|račun)", re.I), DocumentType.ULAZNI_RACUN),
    (re.compile(r"(?:ir|ur)[\s_-]?\d+", re.I), DocumentType.ULAZNI_RACUN),
    (re.compile(r"(?:R|R-)?\d{1,3}[\s_/-]\d{1,2}[\s_/-]\d{1,4}", re.I), DocumentType.ULAZNI_RACUN),

    # Blagajna
    (re.compile(r"(?:blagajn|gotovink|cash|primitak|izdatak)", re.I), DocumentType.BLAGAJNICKI_PRIMAK),

    # Putni nalozi
    (re.compile(r"(?:putni|travel|nalog.*put|loko.*vožnj)", re.I), DocumentType.PUTNI_NALOG),

    # IOS
    (re.compile(r"(?:ios|izvod.*otvoren|open.*balance)", re.I), DocumentType.IOS_OBRAZAC),

    # Ugovori
    (re.compile(r"(?:ugovor|contract|sporazum|aneks)", re.I), DocumentType.UGOVOR),
]

# Ključne riječi u sadržaju dokumenta za klasifikaciju
CONTENT_KEYWORDS: Dict[DocumentType, List[str]] = {
    DocumentType.ULAZNI_RACUN: [
        "pdv", "porez na dodanu vrijednost", "faktura", "ukupno za platiti",
        "račun broj", "r-1", "r-2", "dospijeće", "rok plaćanja",
        "osnovica", "pdv iznos", "obračun pdv", "napomena o pdv",
    ],
    DocumentType.BANKOVNI_IZVOD: [
        "izvod broj", "saldo", "promet", "duguje", "potražuje",
        "iban", "swift", "bic", "mt940", "datum valute",
    ],
    DocumentType.BLAGAJNICKI_PRIMAK: [
        "blagajnički", "gotovinski", "primitak br", "izdatak br",
        "blagajna", "gotovina",
    ],
    DocumentType.PUTNI_NALOG: [
        "putni nalog", "dnevnica", "km naknada", "prijevozno sredstvo",
        "odredište", "svrha putovanja", "polazak", "povratak",
    ],
    DocumentType.IOS_OBRAZAC: [
        "izvod otvorenih stavki", "ios", "usklađivanje",
        "suglasan", "nesuglasan", "otvorene stavke",
    ],
    DocumentType.UGOVOR: [
        "ugovor o", "ugovorne strane", "članak", "aneks",
        "predmet ugovora", "potpisnik",
    ],
}


class DocumentClassifier:
    """
    Klasifikacija dokumenata u tipove za routing.

    Koristi trostupanjski pristup:
      1. Extension check (MT940 → BANKOVNI_IZVOD)
      2. Filename heuristika (regex matching)
      3. Content keyword matching (za PDF-ove s ekstrahiranim tekstom)
      4. Vision AI fallback (za slike bez teksta)
    """

    def __init__(self):
        self._classification_count = 0
        self._confidence_threshold = 0.6
        logger.info("DocumentClassifier inicijaliziran")

    def classify_by_filename(self, filename: str) -> Tuple[DocumentType, float]:
        """Klasificiraj dokument na temelju imena datoteke."""
        for pattern, doc_type in FILENAME_PATTERNS:
            if pattern.search(filename):
                logger.info("Filename match: '%s' → %s", filename, doc_type.value)
                return doc_type, 0.75

        return DocumentType.NEPOZNATO, 0.0

    def classify_by_content(self, text: str) -> Tuple[DocumentType, float]:
        """Klasificiraj na temelju ključnih riječi u tekstu dokumenta."""
        if not text:
            return DocumentType.NEPOZNATO, 0.0

        text_lower = text.lower()
        scores: Dict[DocumentType, int] = {}

        for doc_type, keywords in CONTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[doc_type] = score

        if not scores:
            return DocumentType.NEPOZNATO, 0.0

        # Najbolji match
        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_type]
        total_keywords = len(CONTENT_KEYWORDS[best_type])
        confidence = min(0.95, 0.4 + (best_score / total_keywords) * 0.55)

        logger.info(
            "Content match: %s (score=%d/%d, confidence=%.2f)",
            best_type.value, best_score, total_keywords, confidence,
        )
        return best_type, confidence

    def classify(
        self,
        file_path: str,
        extracted_text: Optional[str] = None,
    ) -> Tuple[DocumentType, float]:
        """
        Kombinirani klasifikator.

        Prioritet:
          1. Filename heuristika (brzo, pouzdano za standardne nazive)
          2. Content matching (ako je tekst dostupan)
          3. NEPOZNATO (zahtijeva Vision AI)
        """
        path = Path(file_path)
        self._classification_count += 1

        # Extension shortcut za specifične formate
        suffix = path.suffix.lower()
        if suffix in (".mt940", ".sta", ".940"):
            return DocumentType.BANKOVNI_IZVOD, 0.95

        # Korak 1: Filename
        fn_type, fn_conf = self.classify_by_filename(path.name)
        if fn_conf >= self._confidence_threshold:
            return fn_type, fn_conf

        # Korak 2: Content
        if extracted_text:
            ct_type, ct_conf = self.classify_by_content(extracted_text)
            if ct_conf >= self._confidence_threshold:
                return ct_type, ct_conf

            # Kombiniraj ako oba daju isti rezultat
            if fn_type == ct_type and fn_type != DocumentType.NEPOZNATO:
                combined = min(0.95, fn_conf + ct_conf)
                return fn_type, combined

            # Content je pouzdaniji od naziva
            if ct_conf > fn_conf:
                return ct_type, ct_conf

        # Korak 3: Vrati filename match ili NEPOZNATO
        if fn_type != DocumentType.NEPOZNATO:
            return fn_type, fn_conf

        return DocumentType.NEPOZNATO, 0.0

    def get_stats(self) -> Dict[str, int]:
        return {"classifications": self._classification_count}
