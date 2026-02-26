"""
Nyx Light — 4-Tier Memory System

L0 (Working): Trenutni kontekst chata
L1 (Episodic): Dnevnik interakcija (sprječava ponavljanje grešaka)
L2 (Semantic): Trajna pravila kontiranja po klijentima
L3 (Nightly DPO): Noćna optimizacija modela

Adaptirano iz Nyx 47.0 Memory System.
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.memory")


class MemorySystem:
    """Centralni memory manager za Nyx Light."""

    def __init__(self):
        from .working import WorkingMemory
        from .episodic import EpisodicMemory
        from .semantic import SemanticMemory

        self.l0_working = WorkingMemory()
        self.l1_episodic = EpisodicMemory()
        self.l2_semantic = SemanticMemory()
        logger.info("4-Tier Memory System inicijaliziran")

    def record_correction(
        self,
        user_id: str,
        client_id: str,
        original_konto: str,
        corrected_konto: str,
        document_type: str,
        supplier: str = "",
        description: str = "",
    ):
        """Zabilježi ispravak knjiženja — temelj učenja."""
        # L1: Spremi epizodu (sprečava istu grešku danas)
        self.l1_episodic.store(
            query=f"Kontiranje {document_type} za {client_id}",
            response=f"Konto {original_konto} → ispravljen u {corrected_konto}",
            user_id=user_id,
            session_id=f"correction_{int(time.time())}",
            metadata={
                "client_id": client_id,
                "supplier": supplier,
                "original": original_konto,
                "corrected": corrected_konto,
                "type": "correction",
            },
        )

        # L2: Stvori trajno pravilo
        rule = (
            f"Klijent {client_id}: {document_type} od dobavljača {supplier} "
            f"knjižiti na konto {corrected_konto} (ne {original_konto})"
        )
        self.l2_semantic.store(
            content=rule,
            domain="kontiranje",
            confidence=0.95,
            topics=[client_id, supplier, document_type],
        )

        logger.info("Ispravak zabilježen: %s → %s (klijent: %s)", 
                     original_konto, corrected_konto, client_id)

    def get_kontiranje_hint(
        self, client_id: str, supplier: str = "", doc_type: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Dohvati prijedlog konta na temelju L2 memorije."""
        results = self.l2_semantic.search(
            topics=[client_id],
            keywords=[supplier] if supplier else None,
            limit=3,
        )
        if results:
            return {
                "hint": results[0].content,
                "confidence": results[0].current_confidence,
                "source": "L2_semantic_memory",
            }
        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "l0_working": self.l0_working.get_stats(),
            "l1_episodic": self.l1_episodic.get_stats() if hasattr(self.l1_episodic, 'get_stats') else {},
            "l2_semantic": self.l2_semantic.get_stats() if hasattr(self.l2_semantic, 'get_stats') else {},
        }
