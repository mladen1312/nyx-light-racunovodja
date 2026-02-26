"""
Modul A3/A7 — Kontiranje i Osnovna sredstva

Prijedlog konta temeljen na L2 semantičkoj memoriji.
Amortizacijske stope prema zakonu.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.kontiranje")


class KontiranjeEngine:
    """AI-potpomognuto kontiranje — predlaže, računovođa odobrava."""

    # Osnovni kontni plan (subset za demo)
    KONTNI_PLAN = {
        "1000": "Osnivački ulog",
        "1200": "Ostale nematerijalne imovine",
        "2200": "Oprema",
        "3100": "Sirovine i materijal",
        "4000": "Dobavljači u zemlji",
        "4300": "Dobavljači u inozemstvu",
        "6200": "Prihodi od prodaje robe",
        "6600": "Ostali prihodi",
        "7000": "Materijalni troškovi",
        "7200": "Troškovi usluga",
        "7300": "Amortizacija",
        "7500": "Troškovi osoblja",
        "7800": "Ostali troškovi",
    }

    AMORTIZACIJSKE_STOPE = {
        "računalna_oprema": 50.0,
        "uredska_oprema": 25.0,
        "namještaj": 20.0,
        "vozila": 20.0,
        "nekretnine": 5.0,
    }

    def suggest_konto(self, description: str, client_id: str = "",
                      supplier: str = "", memory_hint: Dict = None) -> Dict[str, Any]:
        """Predloži konto za knjiženje."""
        # Ako postoji hint iz L2 memorije, koristi ga
        if memory_hint:
            return {
                "suggested_konto": memory_hint.get("hint", ""),
                "confidence": memory_hint.get("confidence", 0.8),
                "source": "L2_semantic_memory",
                "requires_approval": True,
            }

        # Osnovna logika kontiranja
        desc_lower = description.lower()
        if "materijal" in desc_lower or "sirovine" in desc_lower:
            return {"suggested_konto": "7000", "confidence": 0.7, "requires_approval": True}
        if "usluga" in desc_lower or "servis" in desc_lower:
            return {"suggested_konto": "7200", "confidence": 0.7, "requires_approval": True}
        if "amortizacija" in desc_lower:
            return {"suggested_konto": "7300", "confidence": 0.9, "requires_approval": True}

        return {"suggested_konto": "7800", "confidence": 0.3, "requires_approval": True}
