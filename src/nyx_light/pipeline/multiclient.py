"""
Nyx Light — Multi-Client Document Pipeline

Automatski routing ulaznih dokumenata prema klijentu.

Strategije identifikacije klijenta:
  1. OIB match — iz PDF/sken slike izvuci OIB, poveži s registriranim klijentom
  2. IBAN match — prepoznaj IBAN kupca/dobavljača
  3. Folder routing — svaki klijent ima svoj subfolder
  4. Email routing — sender domain → klijent
  5. AI klasifikacija — ChatBridge prepozna kontekst

Pipeline:
  Upload/Email/Folder → Identify Client → Extract Data → Create Booking → Notify
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.pipeline.multiclient")

OIB_PATTERN = re.compile(r'\b(\d{11})\b')
IBAN_HR_PATTERN = re.compile(r'\b(HR\d{19})\b')


class ClientMatcher:
    """Mapira dokument na klijenta."""

    def __init__(self, clients: Optional[List[Dict]] = None):
        # {oib: client_data}
        self._by_oib: Dict[str, Dict] = {}
        # {iban: client_data}
        self._by_iban: Dict[str, Dict] = {}
        # {email_domain: client_data}
        self._by_domain: Dict[str, Dict] = {}
        # {folder_name: client_data}
        self._by_folder: Dict[str, Dict] = {}

        if clients:
            for c in clients:
                self.register_client(c)

    def register_client(self, client: Dict):
        """Registriraj klijenta za matching."""
        oib = client.get("oib", "")
        if oib:
            self._by_oib[oib] = client

        for iban in client.get("ibans", []):
            self._by_iban[iban] = client

        for domain in client.get("email_domains", []):
            self._by_domain[domain.lower()] = client

        folder = client.get("folder_name", "")
        if folder:
            self._by_folder[folder.lower()] = client

    def match(self, document: Dict) -> Tuple[Optional[Dict], str, float]:
        """
        Pokuša identificirati klijenta iz dokumenta.

        Returns: (client_data, method, confidence)
        """
        # Strategy 1: OIB from content
        text = document.get("text", "") + " " + document.get("filename", "")
        oibs = OIB_PATTERN.findall(text)
        for oib in oibs:
            if oib in self._by_oib:
                return self._by_oib[oib], "oib", 0.95

        # Strategy 2: IBAN match
        ibans = IBAN_HR_PATTERN.findall(text)
        for iban in ibans:
            if iban in self._by_iban:
                return self._by_iban[iban], "iban", 0.90

        # Strategy 3: Folder routing
        source_folder = document.get("source_folder", "")
        if source_folder:
            folder_name = Path(source_folder).name.lower()
            if folder_name in self._by_folder:
                return self._by_folder[folder_name], "folder", 0.99

        # Strategy 4: Email domain
        sender = document.get("sender_email", "")
        if sender and "@" in sender:
            domain = sender.split("@")[1].lower()
            if domain in self._by_domain:
                return self._by_domain[domain], "email_domain", 0.85

        # Strategy 5: Filename hint (client code prefix)
        filename = document.get("filename", "")
        for oib, client in self._by_oib.items():
            code = client.get("code", "")
            if code and code.lower() in filename.lower():
                return client, "filename", 0.70

        return None, "none", 0.0


class DocumentPipeline:
    """
    Procesira dolazne dokumente kroz pipeline.

    Faze:
      1. Classify — tip dokumenta (račun, izvod, putni, blagajna)
      2. Match Client — ClientMatcher
      3. Extract — strukturirani podaci (OIB, iznos, datum, PDV)
      4. Route — dispatch u odgovarajući modul (bank_parser, invoice_ocr, ...)
      5. Enqueue — stavi u red za odobrenje
    """

    def __init__(self, client_matcher: Optional[ClientMatcher] = None):
        self.matcher = client_matcher or ClientMatcher()
        self._stats = {
            "total_processed": 0,
            "matched": 0,
            "unmatched": 0,
            "by_type": {},
            "by_client": {},
        }

    def classify_document(self, filename: str, text: str = "", mime_type: str = ""
                          ) -> Dict[str, Any]:
        """Klasificiraj tip dokumenta."""
        fn_lower = filename.lower()
        text_lower = text.lower()

        # Bank statement
        if fn_lower.endswith(".sta") or fn_lower.endswith(".mt940") or \
           "mt940" in fn_lower or "izvod" in fn_lower or "bank" in fn_lower:
            return {"type": "bank_statement", "module": "bank_parser", "confidence": 0.95}

        # XML — e-Račun (check BEFORE generic invoice because XML may contain "invoice")
        if fn_lower.endswith(".xml"):
            if any(kw in text_lower for kw in ["ubl", "crossindustry", "einvoice", "e-racun"]):
                return {"type": "e_racun", "module": "eracuni_parser", "confidence": 0.95}
            return {"type": "xml", "module": "general", "confidence": 0.30}

        # Invoice (PDF/image)
        if any(kw in text_lower for kw in ["račun", "faktura", "invoice", "r-1", "r-2"]):
            return {"type": "invoice", "module": "invoice_ocr", "confidence": 0.85}

        if fn_lower.endswith((".pdf", ".jpg", ".jpeg", ".png", ".tiff")):
            return {"type": "invoice", "module": "invoice_ocr", "confidence": 0.60}

        # Excel/CSV — could be IOS, blagajna, or other
        if fn_lower.endswith((".xlsx", ".xls", ".csv")):
            if any(kw in fn_lower for kw in ["ios", "uskladivanje", "reconcil"]):
                return {"type": "ios", "module": "ios_reconciliation", "confidence": 0.90}
            if any(kw in fn_lower for kw in ["blagajna", "cash"]):
                return {"type": "blagajna", "module": "blagajna", "confidence": 0.85}
            if any(kw in fn_lower for kw in ["putni", "travel"]):
                return {"type": "putni_nalog", "module": "putni_nalozi", "confidence": 0.85}
            return {"type": "spreadsheet", "module": "general", "confidence": 0.40}

        return {"type": "unknown", "module": "general", "confidence": 0.0}

    def process(self, filename: str, text: str = "", source_folder: str = "",
                sender_email: str = "", mime_type: str = "") -> Dict[str, Any]:
        """
        Procesiraj dokument kroz cijeli pipeline.

        Returns dict sa svim informacijama za routing.
        """
        self._stats["total_processed"] += 1

        # 1. Classify
        doc_class = self.classify_document(filename, text, mime_type)

        # 2. Match client
        doc_data = {
            "filename": filename,
            "text": text,
            "source_folder": source_folder,
            "sender_email": sender_email,
        }
        client, match_method, match_conf = self.matcher.match(doc_data)

        if client:
            self._stats["matched"] += 1
            client_id = client.get("id", client.get("oib", "unknown"))
            self._stats["by_client"][client_id] = self._stats["by_client"].get(client_id, 0) + 1
        else:
            self._stats["unmatched"] += 1
            client_id = None

        # 3. Track type
        dtype = doc_class["type"]
        self._stats["by_type"][dtype] = self._stats["by_type"].get(dtype, 0) + 1

        # 4. Extract basic entities
        entities = self._extract_entities(text)

        return {
            "filename": filename,
            "document_type": doc_class["type"],
            "target_module": doc_class["module"],
            "classify_confidence": doc_class["confidence"],
            "client": client,
            "client_id": client_id,
            "match_method": match_method,
            "match_confidence": match_conf,
            "entities": entities,
            "needs_review": match_conf < 0.80 or doc_class["confidence"] < 0.60,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Izvuci osnovne entitete iz teksta."""
        entities = {}

        oibs = OIB_PATTERN.findall(text)
        if oibs:
            entities["oibs"] = list(set(oibs))

        ibans = IBAN_HR_PATTERN.findall(text)
        if ibans:
            entities["ibans"] = list(set(ibans))

        # Amounts (EUR)
        amounts = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:EUR|€|kn)', text)
        if amounts:
            entities["amounts"] = amounts[:5]

        # Dates
        dates = re.findall(r'\b(\d{1,2}\.\d{1,2}\.\d{4})\b', text)
        if dates:
            entities["dates"] = dates[:5]

        return entities

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}
