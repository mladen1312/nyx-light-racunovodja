"""
Modul A6 — Putni nalozi

Provjera km-naknade (0,30 EUR/km) i porezno nepriznatih troškova.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.putni_nalozi")

MAX_KM_RATE = 0.30  # EUR/km


class PutniNalogChecker:
    """Provjera ispravnosti putnih naloga."""

    def validate(self, km: float, km_naknada: float = 0.30,
                 dnevnica: float = 0.0, reprezentacija: float = 0.0) -> Dict[str, Any]:
        warnings = []

        if km_naknada > MAX_KM_RATE:
            warnings.append(
                f"⚠️ Km-naknada {km_naknada:.2f} EUR/km prelazi max {MAX_KM_RATE:.2f} EUR/km"
            )

        naknada_ukupno = km * km_naknada
        
        if reprezentacija > 0:
            warnings.append(
                f"⚠️ Troškovi reprezentacije ({reprezentacija:.2f} EUR) — "
                "provjeriti poreznu priznatost (50% za porez na dobit)"
            )

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "km": km,
            "naknada_ukupno": naknada_ukupno,
        }
