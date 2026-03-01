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

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.drugi_dohodak")


def _d(val) -> "Decimal":
    """Convert to Decimal for precise money calculations."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, float):
        return Decimal(str(val))
    return Decimal(str(val) if val else '0')


def _r2(val) -> float:
    """Round Decimal to 2 places and return float for JSON compat."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Ugovor o djelu, autorski, članovi uprave, neoporezivi iznosi
# ════════════════════════════════════════════════════════

from datetime import date

# Stope doprinosa za drugi dohodak 2026.
# Primatelj plaća:
MIO_I_STOPA = 0.15       # 15% MIO I stup
MIO_II_STOPA = 0.05      # 5% MIO II stup
# Isplatitelj plaća:
ZDRAVSTVENO_STOPA = 0.165  # 16.5% zdravstveno

# Porez na dohodak
DD_POREZ_STOPA = 0.20   # 20% (paušalno, bez osobnog odbitka)

# Autorski honorar — paušalni troškovi (čl. 46 Pravilnika)
AUTORSKI_PAUSALNI_TROSKOVI = {
    "likovna_djela": 0.55,          # 55% priznatih troškova
    "knjizevna_proza": 0.40,        # 40%
    "strucni_prijevod": 0.30,       # 30%
    "fotografija": 0.40,            # 40%
    "glazbena_djela": 0.50,         # 50%
    "arhitektura": 0.25,            # 25%
    "software": 0.30,               # 30%
    "ostalo": 0.30,                 # 30% default
}

# Neoporezivi primitci za drugi dohodak 2026.
NEOPOREZIVI_NAGRADE = {
    "sportski_sudac": 40.0,          # EUR po natjecanju
    "nagrada_ucenici": 232.27,       # EUR godišnje
    "naknada_volonterima": 232.27,   # EUR godišnje
    "nagrada_natjecanje": 331.81,    # EUR godišnje
}


class DrugiDohodakCalculator:
    """Obračun drugog dohotka — ugovor o djelu, autorski, članovi uprave."""

    def __init__(self):
        self._count = 0

    def obracun_ugovor_o_djelu(
        self,
        bruto_naknada: float,
        prirez_pct: float = 0.0,
    ) -> dict:
        """Obračun za ugovor o djelu."""
        bruto = _d(bruto_naknada)

        mio_i = _r2(bruto * _d(MIO_I_STOPA))
        mio_ii = _r2(bruto * _d(MIO_II_STOPA))
        dohodak = _r2(bruto - _d(mio_i) - _d(mio_ii))

        porez = _r2(_d(dohodak) * _d(DD_POREZ_STOPA))
        prirez = _r2(_d(porez) * _d(prirez_pct) / _d(100))
        neto = _r2(_d(dohodak) - _d(porez) - _d(prirez))

        zdravstveno = _r2(bruto * _d(ZDRAVSTVENO_STOPA))
        trosak_isplatitelja = _r2(bruto + _d(zdravstveno))

        self._count += 1
        return {
            "tip": "ugovor_o_djelu",
            "bruto": float(bruto),
            "mio_i_15pct": mio_i,
            "mio_ii_5pct": mio_ii,
            "dohodak": dohodak,
            "porez_20pct": porez,
            "prirez": prirez,
            "neto_za_isplatu": neto,
            "zdravstveno_16_5pct": zdravstveno,
            "ukupni_trosak_isplatitelja": trosak_isplatitelja,
            "joppd_oznaka": "4002",  # Oznaka za JOPPD
        }

    def obracun_autorski(
        self,
        bruto_naknada: float,
        vrsta_djela: str = "ostalo",
        prirez_pct: float = 0.0,
    ) -> dict:
        """Obračun autorskog honorara s paušalnim troškovima."""
        bruto = _d(bruto_naknada)

        # Paušalni troškovi
        pct_troskovi = AUTORSKI_PAUSALNI_TROSKOVI.get(vrsta_djela, 0.30)
        pausalni_troskovi = _r2(bruto * _d(pct_troskovi))

        mio_i = _r2(bruto * _d(MIO_I_STOPA))
        mio_ii = _r2(bruto * _d(MIO_II_STOPA))
        dohodak = _r2(bruto - _d(mio_i) - _d(mio_ii) - _d(pausalni_troskovi))

        porez = _r2(_d(dohodak) * _d(DD_POREZ_STOPA))
        prirez = _r2(_d(porez) * _d(prirez_pct) / _d(100))
        neto = _r2(_d(dohodak) - _d(porez) - _d(prirez))

        # Dodaj natrag paušalne troškove (dio koji primatelj zadrži)
        za_isplatu = _r2(_d(neto) + _d(pausalni_troskovi))

        zdravstveno = _r2(bruto * _d(ZDRAVSTVENO_STOPA))
        trosak_isplatitelja = _r2(bruto + _d(zdravstveno))

        self._count += 1
        return {
            "tip": "autorski_honorar",
            "vrsta_djela": vrsta_djela,
            "bruto": float(bruto),
            "pausalni_troskovi_pct": pct_troskovi * 100,
            "pausalni_troskovi": pausalni_troskovi,
            "mio_i_15pct": mio_i,
            "mio_ii_5pct": mio_ii,
            "dohodak": dohodak,
            "porez_20pct": porez,
            "prirez": prirez,
            "neto": neto,
            "za_isplatu": za_isplatu,
            "zdravstveno_16_5pct": zdravstveno,
            "ukupni_trosak_isplatitelja": trosak_isplatitelja,
            "joppd_oznaka": "4042",  # Autorski JOPPD
        }

    def obracun_clan_uprave(
        self,
        bruto_naknada: float,
        prirez_pct: float = 0.0,
    ) -> dict:
        """Obračun naknade za članove uprave/nadzornog odbora."""
        bruto = _d(bruto_naknada)
        # Članovi uprave: nema MIO doprinosa, samo porez + zdravstveno
        porez = _r2(bruto * _d(DD_POREZ_STOPA))
        prirez = _r2(_d(porez) * _d(prirez_pct) / _d(100))
        neto = _r2(bruto - _d(porez) - _d(prirez))

        zdravstveno = _r2(bruto * _d(ZDRAVSTVENO_STOPA))

        self._count += 1
        return {
            "tip": "clan_uprave",
            "bruto": float(bruto),
            "mio_i": 0.0,
            "mio_ii": 0.0,
            "porez_20pct": porez,
            "prirez": prirez,
            "neto_za_isplatu": neto,
            "zdravstveno_16_5pct": zdravstveno,
            "ukupni_trosak": _r2(bruto + _d(zdravstveno)),
            "joppd_oznaka": "4080",
            "napomena": "Članovi uprave: bez doprinosa za MIO",
        }

    def get_stats(self):
        return {"obracun_count": self._count}
