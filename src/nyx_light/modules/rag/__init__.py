"""
Nyx Light — Time-Aware RAG (Retrieval-Augmented Generation)
════════════════════════════════════════════════════════════
Pretraga zakona RH s vremenskim kontekstom.

Ključna inovacija: sustav zna KOJA VERZIJA zakona je važila
u trenutku nastanka poslovnog događaja.

Primjer:
  "Kolika je stopa PDV-a na računalnu opremu kupljenu 15.03.2024.?"
  → Sustav zna da je 15.03.2024. stopa bila 25% (čl. 38 ZPDV)
  → Ali ako se pita za 2014., zna da je bila ranije 25% s ranijim člankom

Zakonska baza:
  - Zakon o računovodstvu (ZOR) — NN 78/15, 134/15, 120/16, 116/18
  - ZPDV — NN 73/13 i naknadne izmjene
  - Zakon o porezu na dobit — NN 177/04 i izmjene
  - Zakon o porezu na dohodak — NN 115/16, 106/18, 121/19
  - Opći porezni zakon — NN 115/16
  - Zakon o fiskalizaciji — NN 133/12, izmjene 2024-2026
  - RPC 2023 — Računski plan za poduzetnike
  - Mišljenja Porezne uprave

Tehnologija:
  - Qdrant vektorska baza za semantičku pretragu
  - bge-m3 multilingual embedding model
  - Temporal filtering — svaki chunk ima valid_from/valid_to
  - Citation tracking — svaki odgovor citira izvor i NN broj
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.rag")


# ═══════════════════════════════════════════
# ZAKONSKE KATEGORIJE
# ═══════════════════════════════════════════

class LawCategory(str, Enum):
    """Kategorije zakonskih propisa."""
    RACUNOVODSTVO = "racunovodstvo"       # Zakon o računovodstvu
    PDV = "pdv"                           # Zakon o PDV-u
    POREZ_DOBIT = "porez_dobit"           # Porez na dobit
    POREZ_DOHODAK = "porez_dohodak"       # Porez na dohodak
    OPCI_POREZNI = "opci_porezni"         # Opći porezni zakon
    FISKALIZACIJA = "fiskalizacija"       # Fiskalizacija
    DEVIZNO = "devizno"                   # Devizno poslovanje
    RADNO_PRAVO = "radno_pravo"           # Zakon o radu (samo plaće)
    KONTNI_PLAN = "kontni_plan"           # RPC 2023
    MISLJENJE_PU = "misljenje_pu"         # Mišljenja Porezne uprave
    PRAVILNIK = "pravilnik"               # Pravilnici
    EU_DIREKTIVA = "eu_direktiva"         # EU direktive


class RelevanceLevel(str, Enum):
    EXACT = "exact"         # Točno pogođen članak
    HIGH = "high"           # Visoka relevantnost
    MEDIUM = "medium"       # Srednja
    LOW = "low"             # Niska
    EXPIRED = "expired"     # Verzija zakona koja više ne vrijedi


# ═══════════════════════════════════════════
# ZAKONSKI CHUNK
# ═══════════════════════════════════════════

@dataclass
class LawChunk:
    """Jedan segment zakona s vremenskim kontekstom."""
    chunk_id: str = ""
    law_name: str = ""              # "Zakon o PDV-u"
    law_short: str = ""             # "ZPDV"
    nn_reference: str = ""          # "NN 73/13, 143/14, 115/16"
    category: LawCategory = LawCategory.PDV
    article: str = ""               # "čl. 38" ili "čl. 79 st. 1"
    title: str = ""                 # Naslov članka
    content: str = ""               # Puni tekst
    summary: str = ""               # Kratki sažetak

    # Vremenski kontekst
    valid_from: str = ""            # ISO datum od kad vrijedi
    valid_to: str = ""              # ISO datum do kad (prazno = još vrijedi)
    amendment_nn: str = ""          # NN izmjene

    # Embedding
    embedding: List[float] = field(default_factory=list)

    @property
    def is_current(self) -> bool:
        """Je li ova verzija trenutno na snazi?"""
        if not self.valid_to:
            return True
        try:
            return date.fromisoformat(self.valid_to) >= date.today()
        except (ValueError, TypeError):
            return True

    def was_valid_on(self, query_date: str) -> bool:
        """Je li ova verzija važila na dani datum?"""
        try:
            qd = date.fromisoformat(query_date)
            vf = date.fromisoformat(self.valid_from) if self.valid_from else date.min
            vt = date.fromisoformat(self.valid_to) if self.valid_to else date.max
            return vf <= qd <= vt
        except (ValueError, TypeError):
            return self.is_current

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "law_name": self.law_name,
            "law_short": self.law_short,
            "nn_reference": self.nn_reference,
            "category": self.category.value,
            "article": self.article,
            "title": self.title,
            "content": self.content[:500],
            "summary": self.summary,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "is_current": self.is_current,
        }


@dataclass
class RAGResult:
    """Rezultat RAG pretrage."""
    query: str = ""
    query_date: str = ""  # Datum poslovnog događaja
    chunks: List[LawChunk] = field(default_factory=list)
    relevance_scores: List[float] = field(default_factory=list)
    answer: str = ""
    citations: List[str] = field(default_factory=list)
    search_time_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_date": self.query_date,
            "answer": self.answer,
            "citations": self.citations,
            "chunks_found": len(self.chunks),
            "search_time_ms": round(self.search_time_ms, 1),
            "sources": [c.to_dict() for c in self.chunks[:5]],
        }


# ═══════════════════════════════════════════
# ZAKONSKA BAZA (Seed Data)
# ═══════════════════════════════════════════

# Pre-loaded zakonske odredbe — bitne za računovodstvo
HR_LAW_DATABASE: List[Dict[str, Any]] = [
    # ── PDV ──
    {
        "law_name": "Zakon o porezu na dodanu vrijednost",
        "law_short": "ZPDV",
        "nn_reference": "NN 73/13, 143/14, 115/16, 106/18, 121/19, 138/20",
        "category": "pdv",
        "article": "čl. 38 st. 1",
        "title": "Stope PDV-a",
        "content": "PDV se obračunava i plaća po stopi od 25% na poreznu osnovicu za sve isporuke dobara i usluga, osim onih za koje je propisana snižena stopa.",
        "summary": "Opća stopa PDV-a iznosi 25%.",
        "valid_from": "2013-07-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o porezu na dodanu vrijednost",
        "law_short": "ZPDV",
        "nn_reference": "NN 73/13",
        "category": "pdv",
        "article": "čl. 38 st. 3",
        "title": "Snižena stopa PDV-a 13%",
        "content": "PDV se obračunava po sniženoj stopi od 13% na ugostiteljske usluge, novine, časopise, jestivo ulje, dječju hranu, vode (osim mineralnih), kino ulaznice.",
        "summary": "Snižena stopa 13% za ugostiteljstvo, novine, kino.",
        "valid_from": "2014-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o porezu na dodanu vrijednost",
        "law_short": "ZPDV",
        "nn_reference": "NN 73/13",
        "category": "pdv",
        "article": "čl. 38 st. 4",
        "title": "Snižena stopa PDV-a 5%",
        "content": "PDV se obračunava po sniženoj stopi od 5% na kruh, mlijeko, lijekove, ortopedska pomagala, knjige, znanstvene časopise, ulaznice za koncerte.",
        "summary": "Snižena stopa 5% za kruh, mlijeko, lijekove, knjige.",
        "valid_from": "2013-07-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o porezu na dodanu vrijednost",
        "law_short": "ZPDV",
        "nn_reference": "NN 73/13",
        "category": "pdv",
        "article": "čl. 79 st. 1",
        "title": "Obvezni sadržaj računa",
        "content": "Račun mora sadržavati: (1) broj i datum računa, (2) ime i prezime ili naziv, adresu i OIB isporučitelja, (3) ime i prezime ili naziv, adresu i OIB primatelja, (4) količinu i uobičajeni naziv isporučenih dobara ili vrstu i količinu obavljenih usluga, (5) datum isporuke dobara ili obavljanja usluga, (6) iznos naknade raščlanjen po stopi PDV-a, (7) stopu PDV-a, (8) iznos PDV-a, (9) ukupan iznos naknade.",
        "summary": "Obvezni elementi računa: OIB, iznosi, PDV, datumi.",
        "valid_from": "2013-07-01",
        "valid_to": "",
    },
    # ── Računovodstvo ──
    {
        "law_name": "Zakon o računovodstvu",
        "law_short": "ZOR",
        "nn_reference": "NN 78/15, 134/15, 120/16, 116/18",
        "category": "racunovodstvo",
        "article": "čl. 7",
        "title": "Poslovne knjige",
        "content": "Poduzetnik je dužan voditi dnevnik, glavnu knjigu i pomoćne knjige. Poslovne knjige vode se sukladno propisima o računovodstvu, poreznim propisima i Hrvatskim standardima financijskog izvještavanja.",
        "summary": "Obveza vođenja dnevnika, glavne knjige i pomoćnih knjiga.",
        "valid_from": "2016-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o računovodstvu",
        "law_short": "ZOR",
        "nn_reference": "NN 78/15",
        "category": "racunovodstvo",
        "article": "čl. 19",
        "title": "Financijski izvještaji",
        "content": "Godišnji financijski izvještaji obuhvaćaju bilancu, račun dobiti i gubitka, izvještaj o novčanim tokovima, izvještaj o promjenama kapitala i bilješke uz financijske izvještaje.",
        "summary": "GFI: bilanca, RDG, NTI, promjene kapitala, bilješke.",
        "valid_from": "2016-01-01",
        "valid_to": "",
    },
    # ── Porez na dobit ──
    {
        "law_name": "Zakon o porezu na dobit",
        "law_short": "ZPD",
        "nn_reference": "NN 177/04, 90/05, 57/06, 80/10, 22/12, 148/13, 143/14, 50/16, 115/16, 106/18, 121/19, 32/20, 138/20",
        "category": "porez_dobit",
        "article": "čl. 28",
        "title": "Stopa poreza na dobit",
        "content": "Porez na dobit plaća se po stopi od 18% na poreznu osnovicu. Porezni obveznici koji ostvaruju prihode do 1.000.000,00 EUR plaćaju porez po stopi od 10%.",
        "summary": "Stopa poreza na dobit: 18% (ili 10% za prihode do 1M EUR).",
        "valid_from": "2023-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o porezu na dobit",
        "law_short": "ZPD",
        "nn_reference": "NN 177/04",
        "category": "porez_dobit",
        "article": "čl. 28",
        "title": "Stopa poreza na dobit (stara)",
        "content": "Porez na dobit plaća se po stopi od 20% na poreznu osnovicu.",
        "summary": "Stara stopa poreza na dobit: 20%.",
        "valid_from": "2005-01-01",
        "valid_to": "2016-12-31",
    },
    # ── Fiskalizacija ──
    {
        "law_name": "Zakon o fiskalizaciji u prometu gotovinom",
        "law_short": "ZFisk",
        "nn_reference": "NN 133/12, 115/16, 32/20, 138/20",
        "category": "fiskalizacija",
        "article": "čl. 1",
        "title": "Predmet zakona",
        "content": "Ovim se zakonom uređuje postupak fiskalizacije, izdavanje računa, sadržaj računa, rokovi za dostavu podataka, te ovlaštenja i dužnosti obveznika fiskalizacije.",
        "summary": "Regulira obveznu fiskalizaciju gotovinskog prometa.",
        "valid_from": "2013-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o fiskalizaciji",
        "law_short": "ZFisk",
        "nn_reference": "Izmjena 2025",
        "category": "fiskalizacija",
        "article": "čl. 15a",
        "title": "Fiskalizacija 2.0 — strukturirani e-račun",
        "content": "Od 1. siječnja 2026. obveznici fiskalizacije koji ispostavljaju račune subjektima javne nabave (B2G) dužni su koristiti strukturirani e-račun u formatu sukladnom europskoj normi EN 16931-1:2017.",
        "summary": "Od 1.1.2026. obvezni e-računi za B2G prema EN 16931.",
        "valid_from": "2026-01-01",
        "valid_to": "",
    },
    # ── Dohodak ──
    {
        "law_name": "Zakon o porezu na dohodak",
        "law_short": "ZDOH",
        "nn_reference": "NN 115/16, 106/18, 121/19, 32/20, 138/20",
        "category": "porez_dohodak",
        "article": "čl. 24",
        "title": "Stope poreza na dohodak",
        "content": "Porez na dohodak plaća se po stopi od 20% na poreznu osnovicu do 50.400,00 EUR godišnje i po stopi od 30% na dio porezne osnovice koji prelazi iznos od 50.400,00 EUR godišnje.",
        "summary": "Porez na dohodak: 20% do 50.400 EUR, 30% iznad.",
        "valid_from": "2023-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Zakon o porezu na dohodak",
        "law_short": "ZDOH",
        "nn_reference": "NN 115/16",
        "category": "porez_dohodak",
        "article": "čl. 14",
        "title": "Osobni odbitak",
        "content": "Osnovni osobni odbitak iznosi 560,00 EUR mjesečno. Osobni odbitak uvećava se za uzdržavane članove obitelji i djecu.",
        "summary": "Osobni odbitak: 560 EUR/mj + uvećanja za obitelj.",
        "valid_from": "2023-01-01",
        "valid_to": "",
    },
    # ── Gotovinski limit ──
    {
        "law_name": "Zakon o sprječavanju pranja novca i financiranja terorizma",
        "law_short": "ZSPNFT",
        "nn_reference": "NN 108/17, 39/19",
        "category": "opci_porezni",
        "article": "čl. 58",
        "title": "Gotovinska ograničenja",
        "content": "Zabranjeno je plaćanje gotovinom u iznosu jednakom ili većem od 10.000 EUR za pravne osobe i fizičke osobe obrtnike. Transakcije iznad 15.000 EUR podliježu obveznoj prijavi.",
        "summary": "Limit gotovine: 10.000 EUR (zabrana), 15.000 EUR (obvezna prijava).",
        "valid_from": "2018-01-01",
        "valid_to": "",
    },
    # ── Putni nalog ──
    {
        "law_name": "Pravilnik o porezu na dohodak",
        "law_short": "PPD",
        "nn_reference": "NN 10/17, 128/17, 106/18, 1/19",
        "category": "pravilnik",
        "article": "čl. 13 st. 2",
        "title": "Naknada za korištenje privatnog automobila",
        "content": "Neoporeziva naknada za korištenje privatnog automobila u službene svrhe iznosi do 0,40 EUR po prijeđenom kilometru (od 1.1.2025. — prethodno 0,30 EUR).",
        "summary": "Kilometraža: 0,40 EUR/km neoporezivo (od 2025.), ranije 0,30 EUR.",
        "valid_from": "2025-01-01",
        "valid_to": "",
    },
    {
        "law_name": "Pravilnik o porezu na dohodak",
        "law_short": "PPD",
        "nn_reference": "NN 10/17",
        "category": "pravilnik",
        "article": "čl. 13 st. 2 (stari)",
        "title": "Naknada za korištenje privatnog automobila (stara)",
        "content": "Neoporeziva naknada za korištenje privatnog automobila u službene svrhe iznosi do 0,30 EUR po prijeđenom kilometru.",
        "summary": "Kilometraža: 0,30 EUR/km neoporezivo (do kraja 2024.).",
        "valid_from": "2017-01-01",
        "valid_to": "2024-12-31",
    },
    # ── Kontni plan ──
    {
        "law_name": "Računski plan za poduzetnike",
        "law_short": "RPC 2023",
        "nn_reference": "HSFI",
        "category": "kontni_plan",
        "article": "Razred 0-9",
        "title": "Struktura kontnog plana",
        "content": "Razred 0: Dugotrajna imovina. Razred 1: Kratkotrajna imovina. Razred 2: Kratkoročne obveze. Razred 3: Zalihe. Razred 4: Troškovi. Razred 5: Interni obračuni. Razred 6: Prihodi po vrstama. Razred 7: Rashodi po vrstama. Razred 8: Rezultat poslovanja. Razred 9: Vlastiti kapital.",
        "summary": "10 razreda: 0-Dugotrajna, 1-Kratkotrajna, 2-Obveze, ..., 9-Kapital.",
        "valid_from": "2023-01-01",
        "valid_to": "",
    },
]


# ═══════════════════════════════════════════
# TIME-AWARE RAG ENGINE
# ═══════════════════════════════════════════

class TimeAwareRAG:
    """
    Pretraga zakona RH s vremenskim kontekstom.

    Workflow:
    1. Korisnik pita: "Kolika je km naknada za putni nalog iz prosinca 2024.?"
    2. RAG prepoznaje: datum = 2024-12-XX → traži verziju zakona za 2024.
    3. Vraća: 0,30 EUR/km (stara verzija)
    4. Napominje: "Od 1.1.2025. naknada je 0,40 EUR/km"
    """

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join(
            os.environ.get("NYX_DATA_DIR", "/tmp/nyx-data"), "laws.db")
        self._chunks: List[LawChunk] = []
        self._lock = threading.Lock()
        self._init_db()
        self._load_seed_data()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS law_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    law_name TEXT NOT NULL,
                    law_short TEXT NOT NULL,
                    nn_reference TEXT,
                    category TEXT NOT NULL,
                    article TEXT,
                    title TEXT,
                    content TEXT NOT NULL,
                    summary TEXT,
                    valid_from TEXT,
                    valid_to TEXT,
                    amendment_nn TEXT,
                    embedding_json TEXT DEFAULT '[]'
                )
            """)
            conn.commit()

    def _load_seed_data(self):
        """Učitaj pre-definirane zakonske odredbe."""
        count = 0
        for entry in HR_LAW_DATABASE:
            chunk = LawChunk(
                chunk_id=hashlib.md5(
                    f"{entry['law_short']}:{entry['article']}:{entry.get('valid_from','')}".encode()
                ).hexdigest()[:12],
                law_name=entry["law_name"],
                law_short=entry["law_short"],
                nn_reference=entry.get("nn_reference", ""),
                category=LawCategory(entry["category"]),
                article=entry.get("article", ""),
                title=entry.get("title", ""),
                content=entry["content"],
                summary=entry.get("summary", ""),
                valid_from=entry.get("valid_from", ""),
                valid_to=entry.get("valid_to", ""),
            )
            self._chunks.append(chunk)
            count += 1

        self._persist_chunks()
        logger.info("Loaded %d law chunks into RAG", count)

    def _persist_chunks(self):
        with sqlite3.connect(self.db_path) as conn:
            for c in self._chunks:
                conn.execute(
                    """INSERT OR REPLACE INTO law_chunks
                       (chunk_id, law_name, law_short, nn_reference, category,
                        article, title, content, summary, valid_from, valid_to)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (c.chunk_id, c.law_name, c.law_short, c.nn_reference,
                     c.category.value, c.article, c.title, c.content,
                     c.summary, c.valid_from, c.valid_to))
            conn.commit()

    def add_chunk(self, chunk: LawChunk):
        """Dodaj novi zakonski chunk."""
        with self._lock:
            self._chunks.append(chunk)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO law_chunks
                       (chunk_id, law_name, law_short, nn_reference, category,
                        article, title, content, summary, valid_from, valid_to)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (chunk.chunk_id, chunk.law_name, chunk.law_short, chunk.nn_reference,
                     chunk.category.value, chunk.article, chunk.title, chunk.content,
                     chunk.summary, chunk.valid_from, chunk.valid_to))
                conn.commit()

    def search(self, query: str, event_date: str = "",
               category: LawCategory = None,
               include_expired: bool = False,
               limit: int = 5) -> RAGResult:
        """
        Pretraga zakona s vremenskim kontekstom.

        Args:
            query: Tekstualni upit
            event_date: Datum poslovnog događaja (ISO format)
            category: Filtriranje po kategoriji zakona
            include_expired: Uključi i stare verzije zakona
            limit: Maksimalan broj rezultata
        """
        start = time.time()
        result = RAGResult(query=query, query_date=event_date)

        # Keyword-based search (production: embedding-based via Qdrant)
        query_lower = query.lower()
        keywords = [w for w in query_lower.split() if len(w) > 2]

        scored_chunks: List[Tuple[LawChunk, float]] = []
        for chunk in self._chunks:
            # Category filter
            if category and chunk.category != category:
                continue

            # Temporal filter
            if event_date:
                if chunk.was_valid_on(event_date):
                    temporal_boost = 1.0
                elif include_expired:
                    temporal_boost = 0.5  # Expired but shown
                else:
                    continue  # Skip expired
            else:
                # No date → prefer current
                temporal_boost = 1.0 if chunk.is_current else 0.3

            # Relevance scoring (keyword match — production: cosine similarity)
            score = 0.0
            searchable = f"{chunk.content} {chunk.title} {chunk.summary} {chunk.article}".lower()
            for kw in keywords:
                if kw in searchable:
                    score += 1.0
                    if kw in chunk.title.lower():
                        score += 0.5
                    if kw in chunk.article.lower():
                        score += 0.3

            if score > 0:
                final_score = score * temporal_boost
                scored_chunks.append((chunk, final_score))

        # Sort by score
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top = scored_chunks[:limit]

        result.chunks = [c for c, _ in top]
        result.relevance_scores = [round(s, 3) for _, s in top]

        # Build citations
        for chunk in result.chunks:
            citation = f"{chunk.law_short} {chunk.article}"
            if chunk.nn_reference:
                citation += f" ({chunk.nn_reference})"
            if not chunk.is_current:
                citation += " [IZVAN SNAGE]"
            result.citations.append(citation)

        # Build answer
        if result.chunks:
            primary = result.chunks[0]
            date_context = f" (za datum {event_date})" if event_date else ""
            result.answer = f"{primary.summary}{date_context}\n\n"
            result.answer += f"Izvor: {primary.law_name}, {primary.article}"
            if primary.nn_reference:
                result.answer += f" ({primary.nn_reference})"

            # Check if there's a newer version
            if event_date and not primary.is_current:
                current = self._find_current_version(primary)
                if current:
                    result.answer += (
                        f"\n\n⚠ NAPOMENA: Od {current.valid_from} vrijedi nova verzija: "
                        f"{current.summary}")
        else:
            result.answer = "Nije pronađen relevantan zakonski propis za vaš upit."

        result.search_time_ms = (time.time() - start) * 1000
        return result

    def _find_current_version(self, chunk: LawChunk) -> Optional[LawChunk]:
        """Pronađi trenutno važeću verziju istog članka."""
        for c in self._chunks:
            if (c.law_short == chunk.law_short and
                c.article.split(" (")[0] == chunk.article.split(" (")[0] and
                c.is_current and c.chunk_id != chunk.chunk_id):
                return c
        return None

    def get_categories(self) -> Dict[str, int]:
        """Vrati broj chunk-ova po kategoriji."""
        counts: Dict[str, int] = {}
        for c in self._chunks:
            key = c.category.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    def get_stats(self) -> Dict[str, Any]:
        current = sum(1 for c in self._chunks if c.is_current)
        return {
            "module": "time_aware_rag",
            "total_chunks": len(self._chunks),
            "current_chunks": current,
            "expired_chunks": len(self._chunks) - current,
            "categories": self.get_categories(),
            "laws_covered": list(set(c.law_short for c in self._chunks)),
        }
