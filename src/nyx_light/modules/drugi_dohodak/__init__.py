"""
Nyx Light — Modul B+: Autorski honorari i Ugovori o djelu

Obračun drugog dohotka:
1. Autorski honorar — neoporezivi dio 30% (čl. 46. st. 5. ZoDohotku)
2. Ugovor o djelu — nema neoporezivog dijela

Doprinosi:
- MIO I (15%) + MIO II (5%) na bruto
- Porez na dohodak 20% na (bruto - doprinosi - osobni odbitak ako je OPZ)
- Prirez prema gradu

Za autorske honorare:
- Bruto = ugovoreni iznos
- Neoporezivi dio = 30% od bruto (za priznate troškove)
- Dohodak = 70% bruto
- MIO = 20% na dohodak
- Porezna osnovica = dohodak - MIO
- Porez = 20% na poreznu osnovicu
- Neto = bruto - MIO - porez - prirez
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.drugi_dohodak")

# Doprinosi
MIO_1_PCT = 15.0  # %
MIO_2_PCT = 5.0   # %
ZDRAVSTVENO_PCT = 7.5  # % za drugi dohodak (na teret isplatitelja)

# Porez
POREZ_STOPA = 20.0
AUTORSKI_NEOPOREZIVI_PCT = 30.0  # Priznati materijalni troškovi


@dataclass
class DrugiDohodakResult:
    """Rezultat obračuna drugog dohotka."""
    ime: str = ""
    oib: str = ""
    vrsta: str = "ugovor_o_djelu"  # ugovor_o_djelu, autorski_honorar
    
    bruto: float = 0.0
    neoporezivi_dio: float = 0.0  # Samo za autorski
    dohodak: float = 0.0
    
    mio_1: float = 0.0  # 15%
    mio_2: float = 0.0  # 5%
    ukupno_mio: float = 0.0
    
    porezna_osnovica: float = 0.0
    porez: float = 0.0
    prirez: float = 0.0
    prirez_stopa: float = 0.0
    ukupno_porez_prirez: float = 0.0
    
    neto: float = 0.0
    
    # Na teret isplatitelja
    zdravstveno: float = 0.0  # 7.5%
    
    # Ukupni trošak za naručitelja
    ukupni_trosak: float = 0.0
    
    warnings: List[str] = field(default_factory=list)
    requires_approval: bool = True


class DrugiDohodakEngine:
    """Obračun autorskih honorara i ugovora o djelu."""

    def __init__(self):
        self._count = 0

    def calculate(
        self,
        ime: str,
        oib: str,
        bruto: float,
        vrsta: str = "ugovor_o_djelu",
        grad: str = "Zagreb",
        prirez_stopa: float = 0.0,
    ) -> DrugiDohodakResult:
        """Obračun drugog dohotka."""
        result = DrugiDohodakResult(
            ime=ime, oib=oib, vrsta=vrsta, bruto=bruto,
        )

        # Neoporezivi dio (samo autorski honorar)
        if vrsta == "autorski_honorar":
            result.neoporezivi_dio = round(bruto * AUTORSKI_NEOPOREZIVI_PCT / 100, 2)
            result.dohodak = round(bruto - result.neoporezivi_dio, 2)
        else:
            result.dohodak = bruto

        # Doprinosi iz dohotka (MIO na teret primatelja)
        result.mio_1 = round(result.dohodak * MIO_1_PCT / 100, 2)
        result.mio_2 = round(result.dohodak * MIO_2_PCT / 100, 2)
        result.ukupno_mio = round(result.mio_1 + result.mio_2, 2)

        # Porezna osnovica
        result.porezna_osnovica = round(result.dohodak - result.ukupno_mio, 2)

        # Porez
        result.porez = round(result.porezna_osnovica * POREZ_STOPA / 100, 2)

        # Prirez
        result.prirez_stopa = prirez_stopa or self._get_prirez(grad)
        result.prirez = round(result.porez * result.prirez_stopa / 100, 2)
        result.ukupno_porez_prirez = round(result.porez + result.prirez, 2)

        # Neto
        result.neto = round(bruto - result.ukupno_mio - result.ukupno_porez_prirez, 2)

        # Zdravstveno na teret isplatitelja
        result.zdravstveno = round(result.dohodak * ZDRAVSTVENO_PCT / 100, 2)

        # Ukupni trošak za naručitelja
        result.ukupni_trosak = round(bruto + result.zdravstveno, 2)

        # Upozorenja
        if bruto > 3_500:
            result.warnings.append(
                "ℹ️ Visoki iznos — provjeriti je li ispravna klasifikacija "
                "(ne bi li trebao biti radni odnos umjesto ugovora o djelu)"
            )

        self._count += 1
        return result

    def booking_lines(self, result: DrugiDohodakResult) -> List[Dict]:
        """Stavke knjiženja za drugi dohodak."""
        lines = []

        # Trošak za naručitelja
        konto_trosak = "5290" if result.vrsta == "ugovor_o_djelu" else "5270"
        lines.append({
            "konto": konto_trosak, "strana": "duguje",
            "iznos": result.bruto,
            "opis": f"{result.vrsta}: {result.ime} — bruto",
        })

        # Zdravstveno na teret isplatitelja
        if result.zdravstveno > 0:
            lines.append({
                "konto": "5290", "strana": "duguje",
                "iznos": result.zdravstveno,
                "opis": f"Zdravstveno 7.5%: {result.ime}",
            })

        # Obveza za neto isplatu
        lines.append({
            "konto": "4290", "strana": "potrazuje",
            "iznos": result.neto,
            "opis": f"Obveza za neto: {result.ime}",
        })

        # Obveza za MIO
        if result.ukupno_mio > 0:
            lines.append({
                "konto": "4210", "strana": "potrazuje",
                "iznos": result.ukupno_mio,
                "opis": f"MIO I+II: {result.ime}",
            })

        # Obveza za porez + prirez
        if result.ukupno_porez_prirez > 0:
            lines.append({
                "konto": "4220", "strana": "potrazuje",
                "iznos": result.ukupno_porez_prirez,
                "opis": f"Porez+prirez: {result.ime}",
            })

        # Obveza za zdravstveno
        if result.zdravstveno > 0:
            lines.append({
                "konto": "4230", "strana": "potrazuje",
                "iznos": result.zdravstveno,
                "opis": f"Zdravstveno na teret isplatitelja: {result.ime}",
            })

        return lines

    def joppd_data(self, result: DrugiDohodakResult) -> Dict[str, Any]:
        """Podaci za JOPPD stranicu B (oznaka 5002/5012)."""
        oznaka = "5012" if result.vrsta == "autorski_honorar" else "5002"
        return {
            "oib": result.oib,
            "oznaka_primitka": oznaka,
            "primitak_bruto": result.bruto,
            "neoporezivi_primitak": result.neoporezivi_dio,
            "dohodak": result.dohodak,
            "mio_1": result.mio_1,
            "mio_2": result.mio_2,
            "porezna_osnovica": result.porezna_osnovica,
            "porez": result.porez,
            "prirez": result.prirez,
            "neto": result.neto,
            "zdravstveno_isplatitelj": result.zdravstveno,
        }

    def _get_prirez(self, grad: str) -> float:
        prirez_map = {
            "zagreb": 18.0, "split": 15.0, "rijeka": 14.0,
            "osijek": 13.0, "zadar": 12.0, "dubrovnik": 10.0,
        }
        return prirez_map.get(grad.lower(), 0.0)

    def get_stats(self):
        return {"drugi_dohodak_calculated": self._count}
