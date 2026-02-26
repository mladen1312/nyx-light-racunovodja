"""
Nyx Light — Qdrant Vektorska Baza za RAG

Pohranjuje i pretražuje chunks zakona RH s vremenskim metapodacima.
Svaki chunk sadrži:
  - text: sadržaj članka/stavka
  - law_name: naziv zakona
  - article_number: broj članka
  - effective_from: datum stupanja na snagu
  - effective_to: datum prestanka važenja (null = još važi)
  - source: NN broj i godina

Koristi sentence-transformers za embeddings.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger("nyx_light.rag.qdrant")

COLLECTION_NAME = "hr_laws"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


@dataclass
class LawChunk:
    """Jedan chunk zakona za vektorsku bazu."""
    text: str
    law_name: str
    article_number: str = ""
    paragraph: str = ""
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    source_nn: str = ""  # Narodne novine referenca
    chunk_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Rezultat pretrage RAG baze."""
    text: str
    law_name: str
    article_number: str
    score: float
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    source_nn: str = ""
    is_active: bool = True


class QdrantStore:
    """
    Qdrant vektorska baza za zakone RH.

    Podržava:
      - Batch ingestion zakona
      - Time-aware search (filtriranje po datumu važenja)
      - Semantic search s embeddingima
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection: str = COLLECTION_NAME,
        embedding_model: str = EMBEDDING_MODEL,
    ):
        self.host = host
        self.port = port
        self.collection = collection
        self.embedding_model_name = embedding_model
        self._client = None
        self._encoder = None
        self._initialized = False
        self._stats = {"documents": 0, "queries": 0, "avg_query_ms": 0.0}
        logger.info("QdrantStore: %s:%d, collection=%s", host, port, collection)

    async def initialize(self) -> bool:
        """Inicijaliziraj konekciju s Qdrant-om i encoder."""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._client = QdrantClient(host=self.host, port=self.port)

            # Kreiraj kolekciju ako ne postoji
            collections = self._client.get_collections().collections
            exists = any(c.name == self.collection for c in collections)

            if not exists:
                self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("Kreirana Qdrant kolekcija: %s", self.collection)
            else:
                info = self._client.get_collection(self.collection)
                self._stats["documents"] = info.points_count
                logger.info(
                    "Qdrant kolekcija postoji: %s (%d dokumenata)",
                    self.collection, info.points_count,
                )

            # Inicijaliziraj encoder
            self._init_encoder()
            self._initialized = True
            return True

        except ImportError:
            logger.error(
                "qdrant-client nije instaliran. "
                "Instalirajte: pip install qdrant-client sentence-transformers",
            )
            return False
        except Exception as e:
            logger.error("Qdrant inicijalizacija neuspješna: %s", e)
            return False

    def _init_encoder(self) -> None:
        """Inicijaliziraj sentence-transformers encoder."""
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.embedding_model_name)
            logger.info("Encoder učitan: %s", self.embedding_model_name)
        except ImportError:
            logger.warning(
                "sentence-transformers nije instaliran. Koristim fallback hash embeddings.",
            )
            self._encoder = None

    def _encode(self, texts: List[str]) -> List[List[float]]:
        """Generiraj embeddings za tekstove."""
        if self._encoder is not None:
            return self._encoder.encode(texts).tolist()

        # Fallback: deterministički hash-based pseudo-embeddings
        # (samo za testiranje, nema semantičku kvalitetu)
        embeddings = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [((b % 200) - 100) / 100.0 for b in h[:EMBEDDING_DIM]]
            # Pad/truncate to EMBEDDING_DIM
            while len(vec) < EMBEDDING_DIM:
                vec.append(0.0)
            embeddings.append(vec[:EMBEDDING_DIM])
        return embeddings

    # ──────────────────────────────────────────────
    # Ingestion
    # ──────────────────────────────────────────────

    async def ingest_chunks(self, chunks: List[LawChunk]) -> Dict[str, Any]:
        """Učitaj listu law chunks u Qdrant."""
        if not self._initialized:
            await self.initialize()

        if not self._client:
            return {"error": "Qdrant klijent nije inicijaliziran", "ingested": 0}

        from qdrant_client.models import PointStruct

        texts = [c.text for c in chunks]
        embeddings = self._encode(texts)

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            payload = {
                "text": chunk.text,
                "law_name": chunk.law_name,
                "article_number": chunk.article_number,
                "paragraph": chunk.paragraph,
                "effective_from": chunk.effective_from.isoformat() if chunk.effective_from else None,
                "effective_to": chunk.effective_to.isoformat() if chunk.effective_to else None,
                "source_nn": chunk.source_nn,
                **chunk.metadata,
            }
            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=embedding,
                    payload=payload,
                )
            )

        # Batch upsert (po 100)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self._client.upsert(collection_name=self.collection, points=batch)

        self._stats["documents"] += len(chunks)
        logger.info("Ingested %d chunks u '%s'", len(chunks), self.collection)

        return {
            "ingested": len(chunks),
            "collection": self.collection,
            "total_documents": self._stats["documents"],
        }

    # ──────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────

    async def search(
        self,
        query: str,
        date_context: Optional[datetime] = None,
        top_k: int = 5,
        law_filter: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Semantička pretraga zakona s vremenskim filtriranjem.

        Args:
            query: Pitanje korisnika
            date_context: Datum poslovnog događaja (za filtriranje verzija zakona)
            top_k: Broj rezultata
            law_filter: Filtriranje po nazivu zakona
        """
        if not self._initialized:
            await self.initialize()

        if not self._client:
            logger.warning("Qdrant nije dostupan, vraćam prazne rezultate")
            return []

        start = time.monotonic()
        self._stats["queries"] += 1

        # Encode query
        query_vector = self._encode([query])[0]

        # Build filter
        must_conditions = []
        if date_context:
            from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

            # effective_from <= date_context
            must_conditions.append(
                FieldCondition(
                    key="effective_from",
                    range=Range(lte=date_context.isoformat()),
                )
            )

        if law_filter:
            from qdrant_client.models import FieldCondition, MatchValue

            must_conditions.append(
                FieldCondition(key="law_name", match=MatchValue(value=law_filter))
            )

        search_filter = None
        if must_conditions:
            from qdrant_client.models import Filter
            search_filter = Filter(must=must_conditions)

        # Search
        results = self._client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=top_k,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        self._stats["avg_query_ms"] = (
            (self._stats["avg_query_ms"] * (self._stats["queries"] - 1) + elapsed_ms)
            / self._stats["queries"]
        )

        # Convert to SearchResult
        search_results = []
        for hit in results:
            payload = hit.payload or {}
            eff_from = None
            eff_to = None
            if payload.get("effective_from"):
                try:
                    eff_from = datetime.fromisoformat(payload["effective_from"])
                except (ValueError, TypeError):
                    pass
            if payload.get("effective_to"):
                try:
                    eff_to = datetime.fromisoformat(payload["effective_to"])
                except (ValueError, TypeError):
                    pass

            is_active = True
            if eff_to and date_context:
                is_active = eff_to >= date_context

            search_results.append(
                SearchResult(
                    text=payload.get("text", ""),
                    law_name=payload.get("law_name", ""),
                    article_number=payload.get("article_number", ""),
                    score=hit.score,
                    effective_from=eff_from,
                    effective_to=eff_to,
                    source_nn=payload.get("source_nn", ""),
                    is_active=is_active,
                )
            )

        logger.info(
            "RAG search: '%s' → %d rezultata (%.1f ms)",
            query[:60], len(search_results), elapsed_ms,
        )
        return search_results

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats}

    async def delete_collection(self) -> bool:
        """Obriši kolekciju (za reset)."""
        if self._client:
            self._client.delete_collection(self.collection)
            self._stats["documents"] = 0
            logger.info("Kolekcija '%s' obrisana", self.collection)
            return True
        return False
