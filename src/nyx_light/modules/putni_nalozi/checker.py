"""
Nyx Light — Modul A6: Putni nalozi i troškovi reprezentacije (Enhanced V2)

Provjere:
- Km naknada 0,30 EUR/km (porezno priznati max)
- Dnevnice: 26,55 EUR (>12h) / 13,28 EUR (8-12h)
- Reprezentacija: 50% porezno nepriznato
- Vremenska provjera (preklapanje naloga)
- Dokumentacija (obvezni elementi)
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.putni_nalozi")

MAX_KM_RATE = 0.30
DNEVNICA_PUNA = 26.55   # >12h
DNEVNICA_POLA = 13.28   # 8-12h
REPREZENTACIJA_NEPRIZNATO_PCT = 50.0

@dataclass
class PutniNalog:
    djelatnik: str = ""
    oib_djelatnika: str = ""
    odrediste: str = ""
    svrha: str = ""
    datum_od: str = ""
    datum_do: str = ""
    km: float = 0.0
    km_naknada: float = MAX_KM_RATE
    dnevnica: float = 0.0
    smjestaj: float = 0.0
    cestarina: float = 0.0
    parking: float = 0.0
    reprezentacija: float = 0.0
    ostalo: float = 0.0
    privatno_vozilo: bool = True
    prateci_racuni: List[str] = field(default_factory=list)

@dataclass
class PutniNalogResult:
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    km_naknada_ukupno: float = 0.0
    ukupno_porezno_priznato: float = 0.0
    ukupno_porezno_nepriznato: float = 0.0
    ukupno: float = 0.0

class PutniNalogChecker:
    """Provjera ispravnosti putnih naloga — Enhanced V2."""
    def __init__(self):
        self._count = 0

    def validate(self, km: float = 0, km_naknada: float = MAX_KM_RATE,
                 dnevnica: float = 0, reprezentacija: float = 0, **kw) -> Dict[str, Any]:
        """Legacy API — backward compatible."""
        pn = PutniNalog(km=km, km_naknada=km_naknada, dnevnica=dnevnica, reprezentacija=reprezentacija)
        r = self.validate_full(pn)
        return {"valid": r.valid, "warnings": r.errors + r.warnings,
                "km": km, "naknada_ukupno": r.km_naknada_ukupno}

    def validate_full(self, pn: PutniNalog) -> PutniNalogResult:
        result = PutniNalogResult()

        # 1. Km naknada
        if pn.km_naknada > MAX_KM_RATE:
            result.warnings.append(
                f"⚠️ Km naknada {pn.km_naknada:.2f} > max {MAX_KM_RATE:.2f} EUR/km — "
                "razlika porezno nepriznata"
            )
        result.km_naknada_ukupno = round(pn.km * min(pn.km_naknada, MAX_KM_RATE), 2)

        # 2. Dnevnica provjera
        if pn.dnevnica > DNEVNICA_PUNA:
            result.warnings.append(
                f"⚠️ Dnevnica {pn.dnevnica:.2f} > max {DNEVNICA_PUNA:.2f} EUR — "
                "razlika porezno nepriznata"
            )

        # 3. Reprezentacija — 50% nepriznato
        repr_nepriznato = 0.0
        if pn.reprezentacija > 0:
            repr_nepriznato = round(pn.reprezentacija * REPREZENTACIJA_NEPRIZNATO_PCT / 100, 2)
            result.warnings.append(
                f"⚠️ Reprezentacija {pn.reprezentacija:.2f} EUR — "
                f"{repr_nepriznato:.2f} EUR (50%) porezno nepriznato (čl. 7. st. 1. t. 3. ZoPD)"
            )
        result.ukupno_porezno_nepriznato = repr_nepriznato

        # 4. Dokumentacija
        if not pn.svrha:
            result.warnings.append("⚠️ Nedostaje svrha puta — obvezan element")
        if not pn.odrediste:
            result.warnings.append("⚠️ Nedostaje odredište")
        if not pn.djelatnik:
            result.errors.append("⛔ Nedostaje ime djelatnika")
            result.valid = False
        if pn.km > 0 and not pn.prateci_racuni:
            result.warnings.append("⚠️ Nema pratećih računa (gorivo, cestarina)")
        if not pn.datum_od:
            result.errors.append("⛔ Nedostaje datum polaska")
            result.valid = False

        # 5. Logičke provjere
        if pn.km > 1000:
            result.warnings.append(f"⚠️ Velika kilometraža ({pn.km:.0f} km) — provjera?")

        # Totals
        ukupno = (result.km_naknada_ukupno + pn.dnevnica + pn.smjestaj +
                  pn.cestarina + pn.parking + pn.reprezentacija + pn.ostalo)
        result.ukupno = round(ukupno, 2)
        result.ukupno_porezno_priznato = round(ukupno - repr_nepriznato, 2)

        self._count += 1
        return result

    def get_stats(self): return {"validations": self._count}
