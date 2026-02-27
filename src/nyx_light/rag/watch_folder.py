"""
Nyx Light — Watch Folder za zakonske dokumente

Korisnik stavlja dokumente u data/incoming_laws/ folder.
Sustav detektira, parsira, i ČEKA potvrdu čovjeka prije
dodavanja u RAG bazu.

Tok:
  1. Korisnik stavi PDF/TXT u data/incoming_laws/
  2. Sustav detektira novi fajl (polling svake 5 sekundi)
  3. AI parsira sadržaj (OCR za PDF)
  4. Identificira koji zakon/pravilnik je relevantan
  5. Stavlja u red za odobrenje (data/incoming_laws/pending/)
  6. Admin odobri → zakon ulazi u RAG bazu
  7. Admin odbije → fajl u data/incoming_laws/rejected/

NIKAD se zakon ne dodaje automatski bez ljudske potvrde!
"""

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.rag.watch_folder")


@dataclass
class IncomingDocument:
    """Dokument koji čeka odobrenje."""
    id: str
    filename: str
    filepath: str
    detected_at: str
    file_hash: str
    file_size_kb: float

    # AI analiza
    detected_law: str = ""           # Koji zakon AI misli da je
    detected_nn: str = ""            # NN broj ako pronađen
    summary: str = ""                # Kratki sažetak
    relevance_score: float = 0.0     # 0-1 koliko je relevantno

    # Status
    status: str = "pending"          # pending, approved, rejected
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "detected_at": self.detected_at,
            "size_kb": round(self.file_size_kb, 1),
            "detected_law": self.detected_law,
            "detected_nn": self.detected_nn,
            "summary": self.summary[:200],
            "relevance_score": round(self.relevance_score, 2),
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
        }


class WatchFolder:
    """
    Prati folder za nove zakonske dokumente.

    Podržava:
      - .pdf (OCR parsing)
      - .txt (direktno čitanje)
      - .docx (tekstualna ekstrakcija)

    Sve prolazi kroz ljudsku potvrdu!
    """

    SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".docx", ".doc", ".htm", ".html"}

    def __init__(self, base_dir: str = "data"):
        self.incoming_dir = Path(base_dir) / "incoming_laws"
        self.pending_dir = self.incoming_dir / "pending"
        self.approved_dir = self.incoming_dir / "approved"
        self.rejected_dir = self.incoming_dir / "rejected"
        self.registry_path = self.incoming_dir / "registry.json"

        # Kreiraj direktorije
        for d in [self.incoming_dir, self.pending_dir,
                  self.approved_dir, self.rejected_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._registry = self._load_registry()
        self._known_hashes: set = {
            doc["file_hash"] for doc in self._registry.get("documents", [])
        }

    def _load_registry(self) -> Dict[str, Any]:
        if self.registry_path.exists():
            try:
                with open(self.registry_path) as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error("Registry corrupted, starting fresh")
        return {"documents": [], "stats": {"total": 0, "approved": 0, "rejected": 0}}

    def _save_registry(self):
        with open(self.registry_path, "w") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)

    def _file_hash(self, filepath: Path) -> str:
        """SHA256 hash datoteke."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def scan_for_new(self) -> List[IncomingDocument]:
        """
        Skeniraj incoming folder za nove datoteke.

        Vraća listu novih dokumenata koji su detektirani.
        Ne dodaje ih automatski u RAG — čekaju ljudsku potvrdu!
        """
        new_docs = []

        for f in self.incoming_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            fhash = self._file_hash(f)
            if fhash in self._known_hashes:
                continue  # Već obrađeno

            # Novi dokument!
            doc_id = f"doc_{int(time.time())}_{fhash[:8]}"
            doc = IncomingDocument(
                id=doc_id,
                filename=f.name,
                filepath=str(f),
                detected_at=datetime.now().isoformat(),
                file_hash=fhash,
                file_size_kb=f.stat().st_size / 1024,
            )

            # AI analiza (placeholder — u produkciji koristi LLM)
            doc = self._analyze_document(doc, f)

            # Premjesti u pending
            pending_path = self.pending_dir / f.name
            shutil.move(str(f), str(pending_path))
            doc.filepath = str(pending_path)
            doc.status = "pending"

            # Registriraj
            self._known_hashes.add(fhash)
            self._registry["documents"].append(doc.to_dict())
            self._registry["stats"]["total"] += 1
            self._save_registry()

            new_docs.append(doc)
            logger.info("Novi dokument detektiran: %s (relevance=%.2f)",
                        f.name, doc.relevance_score)

        return new_docs

    def _analyze_document(self, doc: IncomingDocument,
                          filepath: Path) -> IncomingDocument:
        """
        AI analiza dokumenta — identificira zakon, NN, relevatnost.

        U produkciji ovo koristi LLM za analizu sadržaja.
        Ovdje je placeholder koji čita tekst i traži NN reference.
        """
        text = ""
        try:
            if filepath.suffix.lower() == ".txt":
                text = filepath.read_text(encoding="utf-8", errors="replace")
            elif filepath.suffix.lower() == ".pdf":
                # Placeholder — u produkciji: Vision AI OCR
                text = f"[PDF dokument: {filepath.name}]"
            else:
                text = f"[Dokument: {filepath.name}]"
        except Exception as e:
            logger.error("Greška čitanja %s: %s", filepath, e)
            text = ""

        # Pretraži za NN reference (npr. "NN 151/25")
        import re
        nn_matches = re.findall(r"NN\s*(\d+/\d+)", text)
        if nn_matches:
            doc.detected_nn = ", ".join(nn_matches[:3])
            doc.relevance_score = 0.9

        # Pretraži za ključne riječi
        law_keywords = {
            "PDV": "Zakon o PDV-u",
            "porez na dobit": "Zakon o porezu na dobit",
            "dohodak": "Zakon o porezu na dohodak",
            "fiskalizaci": "Zakon o fiskalizaciji",
            "računovodstv": "Zakon o računovodstvu",
            "doprinosi": "Zakon o doprinosima",
            "plaća": "Uredba o minimalnoj plaći",
            "eRačun": "Zakon o fiskalizaciji (eRačun)",
        }
        for keyword, law_name in law_keywords.items():
            if keyword.lower() in text.lower():
                doc.detected_law = law_name
                doc.relevance_score = max(doc.relevance_score, 0.7)
                break

        if not doc.detected_law:
            doc.detected_law = "Neidentificirano"
            doc.relevance_score = 0.3

        doc.summary = text[:300].replace("\n", " ").strip() if text else "Sadržaj nedostupan"

        return doc

    def approve(self, doc_id: str, reviewer: str,
                notes: str = "") -> Dict[str, Any]:
        """
        Admin odobrava dokument → premjesti u approved/ i dodaj u RAG red.

        Args:
            doc_id: ID dokumenta
            reviewer: Tko je odobrio
            notes: Bilješke

        Returns:
            Status odobrenja
        """
        for doc in self._registry["documents"]:
            if doc["id"] == doc_id:
                if doc["status"] != "pending":
                    return {"ok": False, "error": f"Dokument nije pending (status={doc['status']})"}

                # Premjesti fajl
                old_path = self.pending_dir / doc["filename"]
                new_path = self.approved_dir / doc["filename"]
                if old_path.exists():
                    shutil.move(str(old_path), str(new_path))

                # Ažuriraj status
                doc["status"] = "approved"
                doc["reviewed_by"] = reviewer
                doc["reviewed_at"] = datetime.now().isoformat()
                doc["review_notes"] = notes
                self._registry["stats"]["approved"] += 1
                self._save_registry()

                logger.info("Dokument ODOBREN: %s od %s", doc["filename"], reviewer)
                return {
                    "ok": True,
                    "action": "approved",
                    "filename": doc["filename"],
                    "rag_update_needed": True,
                    "message": f"Dokument '{doc['filename']}' odobren. Spreman za RAG ingestiju.",
                }

        return {"ok": False, "error": f"Dokument {doc_id} nije pronađen"}

    def reject(self, doc_id: str, reviewer: str,
               notes: str = "") -> Dict[str, Any]:
        """Admin odbija dokument."""
        for doc in self._registry["documents"]:
            if doc["id"] == doc_id:
                if doc["status"] != "pending":
                    return {"ok": False, "error": f"Dokument nije pending"}

                old_path = self.pending_dir / doc["filename"]
                new_path = self.rejected_dir / doc["filename"]
                if old_path.exists():
                    shutil.move(str(old_path), str(new_path))

                doc["status"] = "rejected"
                doc["reviewed_by"] = reviewer
                doc["reviewed_at"] = datetime.now().isoformat()
                doc["review_notes"] = notes
                self._registry["stats"]["rejected"] += 1
                self._save_registry()

                logger.info("Dokument ODBIJEN: %s od %s", doc["filename"], reviewer)
                return {"ok": True, "action": "rejected", "filename": doc["filename"]}

        return {"ok": False, "error": f"Dokument {doc_id} nije pronađen"}

    def get_pending(self) -> List[Dict[str, Any]]:
        """Dohvati sve dokumente koji čekaju odobrenje."""
        return [
            doc for doc in self._registry["documents"]
            if doc["status"] == "pending"
        ]

    def get_approved_for_rag(self) -> List[Dict[str, Any]]:
        """Dohvati odobrene dokumente koji trebaju ući u RAG bazu."""
        return [
            doc for doc in self._registry["documents"]
            if doc["status"] == "approved"
        ]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "incoming_dir": str(self.incoming_dir),
            "pending_count": len(self.get_pending()),
            "total_processed": self._registry["stats"]["total"],
            "approved": self._registry["stats"]["approved"],
            "rejected": self._registry["stats"]["rejected"],
        }
