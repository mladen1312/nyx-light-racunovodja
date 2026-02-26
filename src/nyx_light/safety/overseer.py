"""
Nyx Light — OVERSEER za Računovodstvo

Tvrde granice sustava:
1. ZABRANA pravnog savjetovanja izvan obračuna plaća
2. ZABRANA autonomnog knjiženja (Human-in-the-Loop)
3. APSOLUTNA PRIVATNOST (zero cloud)

Adapted from Nyx 47.0 OverseerSafetyMesh.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("nyx_light.safety")


# Zabranjene domene — sustav ODMAH odbija
FORBIDDEN_DOMAINS = [
    "sastavljanje ugovora", "tužba", "sud", "radno pravo",
    "kazneno pravo", "ovrha", "stečaj", "likvidacija",
    "brak", "razvod", "nasljedstvo", "ostavina",
    "odvjetnik", "advokat", "pravni savjet",
]

# Upozoravajuće ključne riječi
WARNING_KEYWORDS = [
    "automatski proknjiži", "proknjiži bez odobrenja",
    "zaobiđi provjeru", "preskoči odobrenje",
    "pošalji u CPP", "pošalji u Synesis",  # bez odobrenja
]


class AccountingOverseer:
    """
    Sigurnosni sustav za Nyx Light — Računovođa.
    
    Implementira 3 tvrde granice + Human-in-the-Loop.
    """

    def __init__(self):
        self._evaluations = 0
        self._blocks = 0
        logger.info("AccountingOverseer inicijaliziran s 3 tvrde granice")

    def evaluate(self, content: str, action_type: str = "query") -> Dict[str, Any]:
        """
        Evaluiraj akciju kroz sigurnosni sustav.
        
        Returns:
            {approved: bool, reason: str, hard_boundary: bool}
        """
        self._evaluations += 1
        content_lower = content.lower()

        # ── TVRDA GRANICA 1: Zabrana pravnog savjetovanja ──
        for forbidden in FORBIDDEN_DOMAINS:
            if forbidden in content_lower:
                self._blocks += 1
                return {
                    "approved": False,
                    "reason": (
                        f"⛔ TVRDA GRANICA: Upit se odnosi na '{forbidden}' "
                        "što je izvan domene računovodstva. "
                        "Nyx Light ne pruža pravne savjete."
                    ),
                    "hard_boundary": True,
                    "boundary_type": "legal_domain",
                }

        # ── TVRDA GRANICA 2: Zabrana autonomnog knjiženja ──
        for warning in WARNING_KEYWORDS:
            if warning in content_lower:
                self._blocks += 1
                return {
                    "approved": False,
                    "reason": (
                        "⛔ TVRDA GRANICA: Zahtjev za autonomno knjiženje. "
                        "Svako knjiženje MORA biti odobreno klikom 'Odobri' "
                        "od strane računovođe. Human-in-the-Loop je obavezan."
                    ),
                    "hard_boundary": True,
                    "boundary_type": "autonomous_booking",
                }

        # ── TVRDA GRANICA 3: Cloud API zabrana ──
        cloud_keywords = ["openai", "anthropic", "chatgpt", "cloud api", "external api"]
        for kw in cloud_keywords:
            if kw in content_lower:
                return {
                    "approved": False,
                    "reason": (
                        "⛔ TVRDA GRANICA: Pristup cloud API-jima je zabranjen. "
                        "Svi podaci (OIB, plaće, poslovne tajne) moraju ostati 100% lokalno."
                    ),
                    "hard_boundary": True,
                    "boundary_type": "privacy",
                }

        # Odobreno
        return {
            "approved": True,
            "reason": "Upit je unutar dozvoljene domene računovodstva.",
            "hard_boundary": False,
        }

    def validate_booking(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """Validiraj prijedlog knjiženja prije odobrenja."""
        warnings = []

        # Provjera limita gotovine
        if booking.get("document_type") == "blagajna":
            iznos = booking.get("iznos", 0)
            if iznos > 10_000:
                warnings.append(
                    f"⚠️ Iznos blagajne ({iznos:.2f} EUR) prelazi limit od 10.000 EUR!"
                )

        # Provjera km-naknade
        if booking.get("document_type") == "putni_nalog":
            km_rate = booking.get("km_naknada", 0)
            if km_rate > 0.30:
                warnings.append(
                    f"⚠️ Km-naknada ({km_rate:.2f} EUR) prelazi max 0,30 EUR/km!"
                )

        # Provjera reprezentacije
        if "reprezentacija" in str(booking.get("opis", "")).lower():
            warnings.append(
                "⚠️ Troškovi reprezentacije — porezno nepriznati iznad limita. "
                "Provjeriti primjenjivost odbitka."
            )

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "requires_approval": True,  # UVIJEK
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "evaluations": self._evaluations,
            "blocks": self._blocks,
            "block_rate": self._blocks / max(1, self._evaluations),
        }
