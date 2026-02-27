"""
Nyx Light — Embedded Vector Store (bez Qdrant servera)

Numpy-based vektorska baza koja radi potpuno lokalno bez eksternog servera.
Koristi sentence-transformers za embeddings, numpy za cosine similarity.

Za produkciju na Mac Studio može se nadograditi na Qdrant, ali ovo je
potpuno funkcionalno za ~1000 law chunks (27 zakona × ~40 članaka).

Persistencija: pickle file u data/rag_db/vectors.pkl
"""

import hashlib
import json
import logging
import pickle
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np

logger = logging.getLogger("nyx_light.rag.embedded")

EMBEDDING_DIM = 384


@dataclass
class LawChunk:
    text: str
    law_name: str
    article_number: str = ""
    paragraph: str = ""
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    source_nn: str = ""
    chunk_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    text: str
    law_name: str
    article_number: str
    score: float
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    source_nn: str = ""
    is_active: bool = True


class EmbeddedVectorStore:
    """
    Lokalna vektorska baza bez eksternih servisa.

    Podržava:
      - Sentence-transformers embeddings (384-dim)
      - Cosine similarity search
      - Time-aware filtering
      - Persistencija na disk (pickle)
      - Fallback na hash embeddings (za testove)
    """

    def __init__(self, persist_dir: str = "data/rag_db"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._persist_path = self.persist_dir / "vectors.pkl"

        self._chunks: List[LawChunk] = []
        self._vectors: Optional[np.ndarray] = None  # (N, 384)
        self._encoder = None
        self._initialized = False
        self._stats = {"documents": 0, "queries": 0, "avg_query_ms": 0.0}

    def initialize(self) -> bool:
        """Inicijaliziraj encoder i učitaj persistirane podatke."""
        # Load encoder
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("Sentence-transformers encoder učitan (384-dim)")
        except ImportError:
            logger.warning("sentence-transformers nije instaliran — koristim hash fallback")
            self._encoder = None

        # Load persisted data
        if self._persist_path.exists():
            try:
                with open(self._persist_path, "rb") as f:
                    data = pickle.load(f)
                self._chunks = data.get("chunks", [])
                self._vectors = data.get("vectors")
                self._stats["documents"] = len(self._chunks)
                logger.info("Učitano %d chunk-ova iz %s", len(self._chunks), self._persist_path)
            except Exception as e:
                logger.error("Greška pri učitavanju vektora: %s", e)

        self._initialized = True
        return True

    def _encode(self, texts: List[str]) -> np.ndarray:
        """Encode texts to vectors."""
        if self._encoder is not None:
            return np.array(self._encoder.encode(texts, show_progress_bar=False))

        # Hash-based fallback (deterministic, no semantic quality)
        vectors = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            # Use hash bytes to generate pseudo-random vector
            np.random.seed(int.from_bytes(h[:4], "big"))
            vec = np.random.randn(EMBEDDING_DIM).astype(np.float32)
            vec /= np.linalg.norm(vec) + 1e-8
            vectors.append(vec)
        return np.array(vectors)

    def ingest_chunks(self, chunks: List[LawChunk]) -> Dict[str, Any]:
        """Dodaj chunk-ove u bazu."""
        if not self._initialized:
            self.initialize()

        if not chunks:
            return {"ingested": 0, "total": len(self._chunks)}

        # Deduplicate by chunk_id
        existing_ids = {c.chunk_id for c in self._chunks}
        new_chunks = [c for c in chunks if c.chunk_id not in existing_ids]

        if not new_chunks:
            return {"ingested": 0, "total": len(self._chunks), "skipped": len(chunks)}

        texts = [c.text for c in new_chunks]
        new_vectors = self._encode(texts)

        self._chunks.extend(new_chunks)

        if self._vectors is not None and len(self._vectors) > 0:
            self._vectors = np.vstack([self._vectors, new_vectors])
        else:
            self._vectors = new_vectors

        self._stats["documents"] = len(self._chunks)

        # Persist
        self._save()

        logger.info("Ingested %d chunks (total: %d)", len(new_chunks), len(self._chunks))
        return {"ingested": len(new_chunks), "total": len(self._chunks)}

    def search(
        self,
        query: str,
        date_context: Optional[datetime] = None,
        top_k: int = 5,
        law_filter: Optional[str] = None,
    ) -> List[SearchResult]:
        """Semantička pretraga s time-aware filterom."""
        if not self._initialized:
            self.initialize()

        if not self._chunks or self._vectors is None:
            return []

        start = time.monotonic()
        self._stats["queries"] += 1

        # Encode query
        query_vec = self._encode([query])[0]

        # Cosine similarity
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True) + 1e-8
        normalized = self._vectors / norms
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-8)
        scores = normalized @ query_norm  # (N,)

        # Filter candidates
        candidates = []
        for i, (chunk, score) in enumerate(zip(self._chunks, scores)):
            # Law filter
            if law_filter and law_filter.lower() not in chunk.law_name.lower():
                continue

            # Time filter
            is_active = True
            if date_context and chunk.effective_to:
                try:
                    eff_to = datetime.fromisoformat(chunk.effective_to)
                    if eff_to < date_context:
                        is_active = False
                except (ValueError, TypeError):
                    pass

            candidates.append((i, float(score), is_active))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Prioritize active chunks
        active = [c for c in candidates if c[2]]
        inactive = [c for c in candidates if not c[2]]
        ranked = (active + inactive)[:top_k]

        results = []
        for idx, score, is_active in ranked:
            chunk = self._chunks[idx]
            results.append(SearchResult(
                text=chunk.text,
                law_name=chunk.law_name,
                article_number=chunk.article_number,
                score=score,
                effective_from=chunk.effective_from,
                effective_to=chunk.effective_to,
                source_nn=chunk.source_nn,
                is_active=is_active,
            ))

        elapsed_ms = (time.monotonic() - start) * 1000
        n = self._stats["queries"]
        self._stats["avg_query_ms"] = (
            (self._stats["avg_query_ms"] * (n - 1) + elapsed_ms) / n
        )

        logger.debug("Search: '%s' → %d results (%.1f ms)", query[:50], len(results), elapsed_ms)
        return results

    def _save(self):
        """Persist to disk."""
        try:
            with open(self._persist_path, "wb") as f:
                pickle.dump({
                    "chunks": self._chunks,
                    "vectors": self._vectors,
                    "timestamp": datetime.now().isoformat(),
                }, f)
        except Exception as e:
            logger.error("Persistencija neuspješna: %s", e)

    def clear(self):
        """Obriši sve podatke."""
        self._chunks = []
        self._vectors = None
        self._stats["documents"] = 0
        self._persist_path.unlink(missing_ok=True)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "has_encoder": self._encoder is not None,
            "persist_path": str(self._persist_path),
            "persist_size_mb": round(self._persist_path.stat().st_size / 1e6, 2)
            if self._persist_path.exists() else 0,
        }
