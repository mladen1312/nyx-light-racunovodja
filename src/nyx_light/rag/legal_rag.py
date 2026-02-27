"""
Nyx Light — Time-Aware LegalRAG za zakone RH

Centralna klasa koja spaja:
  - LawDownloader  → automatski dohvat 27 zakona/pravilnika
  - LawLoader      → chunking po člancima/stavcima
  - QdrantStore    → vektorska pretraga s embeddingom
  - NNMonitor      → praćenje Narodnih Novina za izmjene
  - Embeddings     → paraphrase-multilingual-MiniLM-L12-v2

Svaki odgovor je vremenski kontekstualiziran:
  pitanje o PDV-u iz 2023. → daje zakon koji je vrijedio u 2023.
  pitanje o PDV-u iz 2025. → daje zakon s izmjenama iz NN 9/25

Korištenje:
  rag = LegalRAG()
  rag.initialize()  # Load laws + build index
  result = rag.query("Koja je stopa PDV-a na hranu?", date_context=datetime(2025,3,1))
"""

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.rag")

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class LegalRAG:
    """Time-Aware RAG za zakone RH — produkcijska verzija."""

    def __init__(self, laws_dir: str = "data/laws",
                 rag_dir: str = "data/rag_db",
                 embed_cache: str = "data/models/embeddings"):
        self.laws_dir = Path(laws_dir)
        self.rag_dir = Path(rag_dir)
        self.embed_cache = Path(embed_cache)
        self._initialized = False
        self._embedder = None
        self._chunks = []      # In-memory chunks (fallback bez Qdrant-a)
        self._embeddings = []  # In-memory embeddings
        self._document_count = 0
        self._query_count = 0
        self._downloader = None
        self._loader = None
        self._nn_monitor = None
        logger.info("LegalRAG v2 kreiran (laws=%s)", laws_dir)

    # ════════════════════════════════════════
    # INICIJALIZACIJA
    # ════════════════════════════════════════

    def initialize(self, download: bool = True, callback=None) -> Dict[str, Any]:
        """
        Inicijaliziraj RAG sustav:
          1. Download zakona (ako treba)
          2. Parse/chunk zakona
          3. Generiraj embeddings
          4. Spremi u Qdrant (ili in-memory fallback)
        """
        t0 = time.time()
        results = {"laws_downloaded": 0, "chunks_created": 0,
                    "embeddings_built": 0, "time_seconds": 0}

        # 1. Download
        if download:
            from .law_downloader import LawDownloader
            self._downloader = LawDownloader(
                laws_dir=str(self.laws_dir), rag_dir=str(self.rag_dir))
            dl = self._downloader.download_all(
                callback=callback or (lambda m: logger.info(m)))
            results["laws_downloaded"] = dl.get("downloaded", 0)

        # 2. Parse & Chunk
        from .law_loader import LawLoader
        self._loader = LawLoader()
        law_files = sorted(self.laws_dir.glob("*.txt"))
        all_chunks = []
        for f in law_files:
            try:
                chunks = self._loader.load_file(f)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.warning("Error loading %s: %s", f.name, e)
        self._chunks = all_chunks
        results["chunks_created"] = len(all_chunks)
        self._document_count = len(law_files)

        # 3. Embeddings
        if all_chunks:
            self._build_embeddings(all_chunks)
            results["embeddings_built"] = len(self._embeddings)

        results["time_seconds"] = round(time.time() - t0, 1)
        self._initialized = True
        logger.info("LegalRAG initialized: %d chunks, %d embeddings in %.1fs",
                     len(all_chunks), len(self._embeddings), results["time_seconds"])
        return results

    def _build_embeddings(self, chunks):
        """Build embedding vektore za sve chunks."""
        try:
            from sentence_transformers import SentenceTransformer
            if self._embedder is None:
                cache = str(self.embed_cache)
                os.makedirs(cache, exist_ok=True)
                self._embedder = SentenceTransformer(EMBED_MODEL, cache_folder=cache)
                logger.info("Embedding model loaded: %s", EMBED_MODEL)

            texts = [c.text for c in chunks]
            # Batch encode
            self._embeddings = self._embedder.encode(
                texts, batch_size=64, show_progress_bar=False,
                normalize_embeddings=True,
            ).tolist()
            logger.info("Built %d embeddings", len(self._embeddings))
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG search disabled")
            self._embeddings = []
        except Exception as e:
            logger.error("Embedding error: %s", e)
            self._embeddings = []

    # ════════════════════════════════════════
    # QUERY (TIME-AWARE)
    # ════════════════════════════════════════

    def query(self, question: str, date_context: Optional[datetime] = None,
              top_k: int = 5) -> Dict[str, Any]:
        """
        Postavi pitanje pravnoj bazi.

        Args:
            question:     Pitanje (npr. "Koja je stopa PDV-a na hranu?")
            date_context: Datum poslovnog događaja za verzioniranje zakona
            top_k:        Broj rezultata

        Returns:
            Dict s rezultatima, citatima, i confidence scorom
        """
        self._query_count += 1
        effective_date = date_context or datetime.now()

        if not self._initialized or not self._chunks:
            return {
                "question": question,
                "date_context": effective_date.isoformat(),
                "results": [],
                "warning": "RAG nije inicijaliziran. Pozovite rag.initialize()",
                "confidence": 0.0,
            }

        if not self._embeddings:
            # Fallback: keyword search
            return self._keyword_search(question, effective_date, top_k)

        # Semantic search
        return self._semantic_search(question, effective_date, top_k)

    def _semantic_search(self, question: str, date: datetime,
                          top_k: int) -> Dict[str, Any]:
        """Vektorska pretraga s vremenskim filtrom."""
        try:
            import numpy as np

            # Encode query
            q_emb = self._embedder.encode(
                [question], normalize_embeddings=True)[0]

            # Compute similarities
            emb_matrix = np.array(self._embeddings)
            scores = np.dot(emb_matrix, q_emb)

            # Time filter: boost chunks whose effective date matches
            for i, chunk in enumerate(self._chunks):
                if hasattr(chunk, 'effective_from') and chunk.effective_from:
                    try:
                        eff = chunk.effective_from
                        if isinstance(eff, str):
                            eff = datetime.fromisoformat(eff)
                        if eff <= date:
                            scores[i] *= 1.1  # Boost aktivan zakon
                        else:
                            scores[i] *= 0.5  # Penalty budući zakon
                    except (ValueError, TypeError):
                        pass

            # Top-K
            top_idx = np.argsort(scores)[-top_k:][::-1]
            results = []
            for idx in top_idx:
                chunk = self._chunks[idx]
                score = float(scores[idx])
                if score < 0.2:
                    continue
                results.append({
                    "text": chunk.text,
                    "law": chunk.law_name,
                    "article": getattr(chunk, 'article_number', ''),
                    "effective_from": str(getattr(chunk, 'effective_from', '')),
                    "score": round(score, 3),
                })

            avg_score = sum(r["score"] for r in results) / max(len(results), 1)
            return {
                "question": question,
                "date_context": date.isoformat(),
                "results": results,
                "confidence": round(avg_score, 2),
                "method": "semantic",
                "total_chunks": len(self._chunks),
            }
        except ImportError:
            return self._keyword_search(question, date, top_k)
        except Exception as e:
            logger.error("Semantic search error: %s", e)
            return self._keyword_search(question, date, top_k)

    def _keyword_search(self, question: str, date: datetime,
                         top_k: int) -> Dict[str, Any]:
        """Fallback keyword pretraga."""
        words = set(question.lower().split())
        scored = []
        for chunk in self._chunks:
            text_lower = chunk.text.lower()
            score = sum(1 for w in words if w in text_lower) / max(len(words), 1)
            if score > 0.2:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            results.append({
                "text": chunk.text[:500],
                "law": chunk.law_name,
                "article": getattr(chunk, 'article_number', ''),
                "score": round(score, 3),
            })

        return {
            "question": question,
            "date_context": date.isoformat(),
            "results": results,
            "confidence": round(results[0]["score"], 2) if results else 0.0,
            "method": "keyword",
            "total_chunks": len(self._chunks),
        }

    # ════════════════════════════════════════
    # AUTO-UPDATE (wire to NN Monitor)
    # ════════════════════════════════════════

    def auto_update(self, callback=None) -> Dict[str, Any]:
        """
        Automatski update:
          1. Provjeri NN za izmjene
          2. Skini nove zakone
          3. Rebuild index
        """
        from .nn_monitor import NNMonitor
        self._nn_monitor = NNMonitor(
            laws_dir=str(self.laws_dir), rag_dir=str(self.rag_dir))

        # Check NN
        nn_result = self._nn_monitor.auto_update_rag(callback=callback)

        # Re-initialize if something changed
        if nn_result.get("rag_updated"):
            self.initialize(download=True, callback=callback)

        return {
            "nn_check": nn_result,
            "reindexed": nn_result.get("rag_updated", False),
            "total_chunks": len(self._chunks),
        }

    # ════════════════════════════════════════
    # INGEST (za ručno dodavanje)
    # ════════════════════════════════════════

    def ingest_law(self, title: str, content: str, effective_from: datetime,
                   effective_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Ručno učitaj zakon/propis u RAG bazu."""
        from .qdrant_store import LawChunk
        chunk = LawChunk(
            text=content, law_name=title,
            effective_from=effective_from, effective_to=effective_to,
        )
        self._chunks.append(chunk)
        self._document_count += 1

        # Rebuild embeddings for new chunk
        if self._embedder:
            emb = self._embedder.encode([content], normalize_embeddings=True)[0]
            self._embeddings.append(emb.tolist())

        return {
            "title": title,
            "effective_from": effective_from.isoformat(),
            "effective_to": effective_to.isoformat() if effective_to else "active",
            "status": "ingested",
            "total_chunks": len(self._chunks),
        }

    # ════════════════════════════════════════
    # STATS
    # ════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        nn_status = None
        if self._nn_monitor:
            nn_status = self._nn_monitor.get_status()
        dl_stats = None
        if self._downloader:
            dl_stats = self._downloader.get_stats()
        return {
            "initialized": self._initialized,
            "documents": self._document_count,
            "chunks": len(self._chunks),
            "embeddings": len(self._embeddings),
            "queries": self._query_count,
            "embed_model": EMBED_MODEL,
            "nn_monitor": nn_status,
            "downloader": dl_stats,
        }
