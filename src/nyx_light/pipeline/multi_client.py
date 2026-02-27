"""
Nyx Light — Multi-Client Document Pipeline

Automatsko prepoznavanje i usmjeravanje dokumenata prema klijentu:
  1. Identificiraj klijenta (OIB, naziv, IBAN iz dokumenta)
  2. Klasificiraj dokument (ulazni račun, izvod, putni nalog...)
  3. Usmjeri na odgovarajući modul za obradu
  4. Pripremi za ljudsko odobrenje

Pipeline koristi Module Router + Client Registry za routing.
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.pipeline.multi_client")


@dataclass
class DocumentInfo:
    """Metapodaci o dokumentu u pipeline-u."""
    doc_id: str = ""
    filename: str = ""
    filepath: str = ""
    file_type: str = ""  # pdf, xlsx, csv, xml, sta
    size_bytes: int = 0
    source: str = ""  # email, folder, upload, api
    timestamp: float = 0.0

    # Identificirano
    detected_client_id: str = ""
    detected_client_name: str = ""
    detected_oib: str = ""
    detected_type: str = ""  # ulazni_racun, izvod, putni_nalog, ios, e_racun, other
    confidence: float = 0.0

    # Processing
    status: str = "queued"  # queued, processing, routed, completed, error
    assigned_module: str = ""
    result: Dict = field(default_factory=dict)
    error: str = ""

    def __post_init__(self):
        if not self.doc_id:
            raw = f"{self.filename}_{self.timestamp}_{self.filepath}"
            self.doc_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = time.time()


class ClientMatcher:
    """Prepoznaje klijenta iz sadržaja dokumenta."""

    def __init__(self, clients: List[Dict] = None):
        """
        clients: [{"id": "K001", "name": "Firma d.o.o.", "oib": "12345678901",
                    "ibans": ["HR12..."], "aliases": ["Firma"]}]
        """
        self._clients = clients or []
        self._oib_map: Dict[str, Dict] = {}
        self._iban_map: Dict[str, Dict] = {}
        self._name_patterns: List[Tuple[re.Pattern, Dict]] = []
        self._build_indices()

    def _build_indices(self):
        for c in self._clients:
            oib = c.get("oib", "")
            if oib:
                self._oib_map[oib] = c
            for iban in c.get("ibans", []):
                self._iban_map[iban] = c
            # Name patterns (fuzzy-ish)
            name = c.get("name", "")
            if name:
                escaped = re.escape(name)
                try:
                    self._name_patterns.append((re.compile(escaped, re.IGNORECASE), c))
                except re.error:
                    pass
            for alias in c.get("aliases", []):
                try:
                    self._name_patterns.append((re.compile(re.escape(alias), re.IGNORECASE), c))
                except re.error:
                    pass

    def match(self, text: str) -> Tuple[Optional[Dict], float]:
        """
        Pronađi klijenta u tekstu dokumenta.
        Vraća (client_dict, confidence).
        """
        if not text:
            return None, 0.0

        # 1. OIB match (highest confidence)
        oib_matches = re.findall(r'\b\d{11}\b', text)
        for oib in oib_matches:
            if oib in self._oib_map:
                return self._oib_map[oib], 0.95

        # 2. IBAN match (high confidence)
        iban_matches = re.findall(r'HR\d{19}', text)
        for iban in iban_matches:
            if iban in self._iban_map:
                return self._iban_map[iban], 0.90

        # 3. Name match (medium confidence)
        for pattern, client in self._name_patterns:
            if pattern.search(text):
                return client, 0.75

        return None, 0.0

    def update_clients(self, clients: List[Dict]):
        self._clients = clients
        self._oib_map.clear()
        self._iban_map.clear()
        self._name_patterns.clear()
        self._build_indices()


class DocumentClassifier:
    """Klasificira tip dokumenta."""

    PATTERNS = {
        "bankovni_izvod": [
            r'izvod\s+br', r'MT940', r'SWIFT', r'promet\s+računa',
            r'početno\s+stanje', r'završno\s+stanje', r'valuta\s+terećenja',
        ],
        "ulazni_racun": [
            r'račun\s+br', r'R-\d+', r'faktura', r'invoice',
            r'PDV\s+\d+%', r'ukupno\s+s\s+PDV', r'rok\s+plaćanja',
        ],
        "putni_nalog": [
            r'putni\s+nalog', r'dnevnica', r'km\s+naknada',
            r'relacija', r'svrha\s+put', r'prijevozno\s+sredstvo',
        ],
        "ios_obrazac": [
            r'IOS', r'izvod\s+otvorenih\s+stavk', r'usklađivanje\s+stanja',
            r'otvorene\s+stavke', r'datum\s+usklađ',
        ],
        "e_racun": [
            r'UBL', r'CrossIndustry', r'eRačun', r'e-Račun',
            r'EN\s*16931', r'InvoiceTypeCode',
        ],
        "joppd": [
            r'JOPPD', r'obrazac\s+JOPPD', r'strana\s+[AB]',
            r'oznaka\s+stjecatelja', r'MIO\s+I', r'dohodak',
        ],
        "blagajna": [
            r'blagajna', r'blagajnički', r'uplatnica', r'isplatnica',
            r'gotovinski', r'blagajn',
        ],
        "kompenzacija": [
            r'kompenzacij', r'prijeboj', r'cesija', r'asignacij',
            r'izjava\s+o\s+kompenzacij',
        ],
    }

    def classify(self, text: str, filename: str = "") -> Tuple[str, float]:
        """Klasificiraj dokument po sadržaju i imenu datoteke."""
        text_lower = (text + " " + filename).lower()

        # File extension hints
        ext = Path(filename).suffix.lower() if filename else ""
        if ext in (".sta", ".mt940"):
            return "bankovni_izvod", 0.95
        if ext in (".xml",) and any(p in text_lower for p in ["ubl", "crossindustry"]):
            return "e_racun", 0.90

        # Pattern matching
        scores: Dict[str, int] = {}
        for doc_type, patterns in self.PATTERNS.items():
            score = sum(1 for p in patterns if re.search(p, text_lower))
            if score > 0:
                scores[doc_type] = score

        if not scores:
            return "other", 0.3

        best = max(scores, key=scores.get)
        confidence = min(0.95, 0.5 + scores[best] * 0.15)
        return best, confidence


class MultiClientPipeline:
    """Orkestrira obradu dokumenata za multiple klijente."""

    def __init__(self, clients: List[Dict] = None):
        self.client_matcher = ClientMatcher(clients or [])
        self.classifier = DocumentClassifier()
        self._queue: List[DocumentInfo] = []
        self._processed: List[DocumentInfo] = []
        self._stats = {"total": 0, "routed": 0, "errors": 0, "by_type": {}, "by_client": {}}

    # Module mapping
    MODULE_MAP = {
        "bankovni_izvod": "bank_parser",
        "ulazni_racun": "invoice_ocr",
        "putni_nalog": "putni_nalozi",
        "ios_obrazac": "ios",
        "e_racun": "e_racun",
        "joppd": "joppd",
        "blagajna": "blagajna",
        "kompenzacija": "kompenzacije",
    }

    def ingest(self, filepath: str, source: str = "upload",
               text_content: str = "", client_hint: str = "") -> DocumentInfo:
        """
        Primi dokument u pipeline.

        filepath: putanja do datoteke
        source: email, folder, upload, api
        text_content: ekstrahirani tekst (ako dostupan)
        client_hint: ID klijenta ako je unaprijed poznat
        """
        path = Path(filepath)
        doc = DocumentInfo(
            filename=path.name,
            filepath=str(path),
            file_type=path.suffix.lstrip(".").lower(),
            size_bytes=path.stat().st_size if path.exists() else 0,
            source=source,
        )

        # Klasificiraj
        doc.detected_type, type_conf = self.classifier.classify(text_content, doc.filename)

        # Pronađi klijenta
        if client_hint:
            doc.detected_client_id = client_hint
            doc.confidence = 0.99
        else:
            client, client_conf = self.client_matcher.match(text_content)
            if client:
                doc.detected_client_id = client.get("id", "")
                doc.detected_client_name = client.get("name", "")
                doc.detected_oib = client.get("oib", "")
                doc.confidence = client_conf
            else:
                doc.confidence = type_conf * 0.5  # Lower if no client found

        # Assign module
        doc.assigned_module = self.MODULE_MAP.get(doc.detected_type, "general")
        doc.status = "routed"

        self._queue.append(doc)
        self._stats["total"] += 1
        self._stats["routed"] += 1
        self._stats["by_type"][doc.detected_type] = self._stats["by_type"].get(doc.detected_type, 0) + 1
        if doc.detected_client_id:
            cid = doc.detected_client_id
            self._stats["by_client"][cid] = self._stats["by_client"].get(cid, 0) + 1

        logger.info(f"Pipeline: {doc.filename} → {doc.detected_type} ({doc.assigned_module}) "
                     f"klijent={doc.detected_client_name or '?'} conf={doc.confidence:.2f}")

        return doc

    def get_queue(self, status: str = "", client_id: str = "") -> List[Dict]:
        """Dohvati dokumente u redu."""
        items = self._queue
        if status:
            items = [d for d in items if d.status == status]
        if client_id:
            items = [d for d in items if d.detected_client_id == client_id]
        return [{
            "doc_id": d.doc_id, "filename": d.filename, "type": d.detected_type,
            "client": d.detected_client_name or d.detected_client_id,
            "module": d.assigned_module, "confidence": d.confidence,
            "status": d.status, "source": d.source,
            "time": datetime.fromtimestamp(d.timestamp).strftime("%H:%M:%S"),
        } for d in items]

    def update_clients(self, clients: List[Dict]):
        """Ažuriraj listu klijenata za matching."""
        self.client_matcher.update_clients(clients)

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "queue_size": len(self._queue)}
