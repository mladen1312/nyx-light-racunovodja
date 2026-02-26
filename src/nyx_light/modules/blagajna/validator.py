"""
Modul A5 — Blagajna

Automatska revizija: provjera limita gotovine (10.000 EUR).
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.blagajna")

MAX_CASH_EUR = 10_000.0


class BlagajnaValidator:
    """Validator za blagajničke operacije."""

    def validate(self, iznos: float, tip: str = "isplata") -> Dict[str, Any]:
        warnings = []
        if iznos > MAX_CASH_EUR:
            warnings.append(
                f"⚠️ Iznos {iznos:.2f} EUR prelazi zakonski limit od {MAX_CASH_EUR:.2f} EUR "
                "za gotovinski promet (Zakon o fiskalizaciji)."
            )
        return {"valid": len(warnings) == 0, "warnings": warnings, "iznos": iznos}
