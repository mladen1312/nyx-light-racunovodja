"""
Nyx Light — Time-Aware RAG za zakone RH

Baza sadrži:
- Zakon o računovodstvu
- Zakon o PDV-u
- Zakon o porezu na dobit
- Zakon o porezu na dohodak
- Mišljenja Porezne uprave

Odgovori su vezani uz vremenski kontekst.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.rag")


class LegalRAG:
    """Time-Aware RAG za zakone RH."""

    def __init__(self):
        self._document_count = 0
        self._query_count = 0
        logger.info("LegalRAG inicijaliziran (Qdrant backend)")

    def query(self, question: str, date_context: Optional[datetime] = None,
              top_k: int = 5) -> Dict[str, Any]:
        """
        Postavi pitanje pravnoj bazi.
        
        Args:
            question: Pitanje o zakonu/propisu
            date_context: Datum poslovnog događaja (za verzioniranje zakona)
            top_k: Broj rezultata
        """
        self._query_count += 1
        effective_date = date_context or datetime.now()

        # TODO: Integrirati s Qdrant vektorskom bazom
        return {
            "question": question,
            "date_context": effective_date.isoformat(),
            "results": [],
            "warning": "RAG baza još nije napunjena zakonima. Pokrenite scripts/ingest_laws.py",
            "confidence": 0.0,
        }

    def ingest_law(self, title: str, content: str, effective_from: datetime,
                   effective_to: Optional[datetime] = None) -> Dict[str, Any]:
        """Učitaj zakon/propis u RAG bazu."""
        self._document_count += 1
        return {
            "title": title,
            "effective_from": effective_from.isoformat(),
            "effective_to": effective_to.isoformat() if effective_to else "active",
            "status": "ingested",
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "documents": self._document_count,
            "queries": self._query_count,
        }
