"""
Nyx Light — Obračun Plaća (Croatian Payroll Calculator)

Kompletni obračun plaće za 2026. godinu prema važećim propisima RH.

Stope (2026.):
  MIO I stup: 15%
  MIO II stup: 5%
  Zdravstveno: 16.5% (na teret poslodavca)
  Porez na dohodak: 20% (do 50.400 EUR/god) / 30% (iznad)
  Osobni odbitak: 560 EUR
  Uzdržavani član: koeficijent × 560 EUR
  Prirez: ovisi o gradu (Zagreb 18%, Split 15%, itd.)

Optimizirano za Apple Silicon — čisti Python, <1ms po obračunu.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.place")

# ═══════════════════════════════════════════
# POREZNE TABLICE 2026.
# ═══════════════════════════════════════════

MIO_I_STOPA = 0.15        # 1. stup mirovinskog
MIO_II_STOPA = 0.05       # 2. stup mirovinskog
ZDRAVSTVENO_STOPA = 0.165  # Na teret poslodavca

POREZ_STOPA_1 = 0.20  # Do godišnje osnovice 50.400 EUR
POREZ_STOPA_2 = 0.30  # Iznad
POREZ_GRANICA_GOD = 50_400.00
POREZ_GRANICA_MJ = POREZ_GRANICA_GOD / 12  # 4.200 EUR/mj

OSOBNI_ODBITAK_BAZA = 560.00  # EUR mjesečno

# Koeficijenti za uzdržavane članove (množiti s bazom)
KOEF_UZDRZAVANI = {
    "dijete_1": 0.7,    # 1. dijete
    "dijete_2": 1.0,    # 2. dijete
    "dijete_3": 1.4,    # 3. dijete
    "dijete_4": 1.9,    # 4. dijete
    "dijete_5+": 2.5,   # 5+ dijete
    "suprug": 0.7,      # Supružnik
    "roditelj": 0.7,    # Uzdržavani roditelj
    "invalid_djelomicno": 0.4,  # Djelomična invalidnost
    "invalid_100": 1.5,        # 100% invalidnost
}

# Prirezi gradova (2026.)
PRIREZI = {
    "zagreb": 0.18,
    "split": 0.15,
    "rijeka": 0.15,
    "osijek": 0.13,
    "zadar": 0.12,
    "pula": 0.12,
    "slavonski brod": 0.12,
    "karlovac": 0.12,
    "varazdin": 0.10,
    "varaždin": 0.10,
    "sisak": 0.10,
    "dubrovnik": 0.10,
    "velika gorica": 0.06,
    "samobor": 0.06,
    "bjelovar": 0.12,
    "koprivnica": 0.12,
    "cakovec": 0.10,
    "čakovec": 0.10,
    "vukovar": 0.00,  # Potpomognuto područje
    "default": 0.10,
}

# Neoporezivi primici (godišnji limiti, 2026.)
NEOPOREZIVI = {
    "bozicnica": 700.00,        # Sve prigodne nagrade ukupno
    "dar_djetetu": 133.00,      # Po djetetu
    "dnevnica_rh_pola": 26.54,  # 12-24h
    "km_naknada": 0.40,         # EUR/km
    "otpremnina_mirovina": 1327.00,
    "otpremnina_otkaz_god": 862.00,  # Po godini staža, max 10
    "prehrana_mj": 150.00,
    "prijevoz_km": 0.22,        # EUR/km za osobni auto
    "jubilarna_10": 199.08,
    "jubilarna_15": 265.45,
    "jubilarna_20": 331.81,
    "jubilarna_25": 398.17,
    "jubilarna_30": 464.53,
    "jubilarna_35": 530.89,
}


@dataclass
class UzdrzavaniClan:
    """Uzdržavani član obitelji."""
    tip: str  # dijete_1, dijete_2, suprug, roditelj, invalid_100
    ime: str = ""
    oib: str = ""


@dataclass
class ObracunPlaceInput:
    """Input za obračun jedne plaće."""
    bruto: float
    grad: str = "zagreb"
    uzdrzavani: List[UzdrzavaniClan] = field(default_factory=list)
    osobni_odbitak_faktor: float = 1.0  # Dodatni faktor (invalidnost radnika)
    prekovremeni_sati: float = 0.0
    satnica_bruto: float = 0.0  # Ako nije zadano, izračuna se
    bonus: float = 0.0
    stimulacija: float = 0.0
    regres: float = 0.0  # Neoporezivi dio
    prehrana: float = 0.0  # Neoporezivi dio
    prijevoz: float = 0.0  # Neoporezivi dio
    mjesec: int = 1
    godina: int = 2026


@dataclass
class ObracunPlaceResult:
    """Rezultat obračuna plaće."""
    # Bruto
    bruto_ukupno: float = 0.0
    bruto_osnova: float = 0.0
    prekovremeni: float = 0.0
    bonus: float = 0.0
    stimulacija: float = 0.0

    # Doprinosi iz plaće (na teret radnika)
    mio_i: float = 0.0   # 15%
    mio_ii: float = 0.0  # 5%
    ukupno_doprinosi_radnik: float = 0.0

    # Dohodak
    dohodak: float = 0.0
    osobni_odbitak: float = 0.0
    porezna_osnovica: float = 0.0

    # Porez i prirez
    porez: float = 0.0
    prirez: float = 0.0
    prirez_stopa: float = 0.0
    ukupno_porez_prirez: float = 0.0

    # Neto
    neto: float = 0.0

    # Neoporezivi primici
    neoporezivi_prehrana: float = 0.0
    neoporezivi_prijevoz: float = 0.0
    neoporezivi_regres: float = 0.0
    ukupno_neoporezivi: float = 0.0

    # Za isplatu
    za_isplatu: float = 0.0

    # Doprinosi na plaću (na teret poslodavca)
    zdravstveno: float = 0.0  # 16.5%

    # Ukupni trošak poslodavca
    trosak_poslodavca: float = 0.0

    # JOPPD podaci
    joppd_mio_i: float = 0.0
    joppd_mio_ii: float = 0.0
    joppd_zdravstveno: float = 0.0
    joppd_dohodak: float = 0.0
    joppd_porez: float = 0.0
    joppd_prirez: float = 0.0

    # Detalji
    detalji: Dict[str, Any] = field(default_factory=dict)


class PayrollCalculator:
    """Hrvatski obračun plaća za 2026. godinu."""

    def obracun(self, inp: ObracunPlaceInput) -> ObracunPlaceResult:
        """Izračunaj kompletnu plaću."""
        r = ObracunPlaceResult()

        # 1. Bruto
        r.bruto_osnova = inp.bruto
        r.prekovremeni = inp.prekovremeni_sati * (inp.satnica_bruto * 1.5 if inp.satnica_bruto else 0)
        r.bonus = inp.bonus
        r.stimulacija = inp.stimulacija
        r.bruto_ukupno = r.bruto_osnova + r.prekovremeni + r.bonus + r.stimulacija

        # 2. Doprinosi iz plaće (na teret radnika)
        r.mio_i = round(r.bruto_ukupno * MIO_I_STOPA, 2)
        r.mio_ii = round(r.bruto_ukupno * MIO_II_STOPA, 2)
        r.ukupno_doprinosi_radnik = round(r.mio_i + r.mio_ii, 2)

        # 3. Dohodak
        r.dohodak = round(r.bruto_ukupno - r.ukupno_doprinosi_radnik, 2)

        # 4. Osobni odbitak
        odbitak = OSOBNI_ODBITAK_BAZA * inp.osobni_odbitak_faktor
        for clan in inp.uzdrzavani:
            koef = KOEF_UZDRZAVANI.get(clan.tip, 0.7)
            odbitak += OSOBNI_ODBITAK_BAZA * koef
        r.osobni_odbitak = round(odbitak, 2)

        # 5. Porezna osnovica
        r.porezna_osnovica = max(0, round(r.dohodak - r.osobni_odbitak, 2))

        # 6. Porez na dohodak (progresivni)
        if r.porezna_osnovica <= POREZ_GRANICA_MJ:
            r.porez = round(r.porezna_osnovica * POREZ_STOPA_1, 2)
        else:
            r.porez = round(
                POREZ_GRANICA_MJ * POREZ_STOPA_1 +
                (r.porezna_osnovica - POREZ_GRANICA_MJ) * POREZ_STOPA_2,
                2,
            )

        # 7. Prirez
        grad_lower = inp.grad.lower().strip()
        r.prirez_stopa = PRIREZI.get(grad_lower, PRIREZI["default"])
        r.prirez = round(r.porez * r.prirez_stopa, 2)
        r.ukupno_porez_prirez = round(r.porez + r.prirez, 2)

        # 8. Neto
        r.neto = round(r.dohodak - r.ukupno_porez_prirez, 2)

        # 9. Neoporezivi primici
        r.neoporezivi_prehrana = min(inp.prehrana, NEOPOREZIVI["prehrana_mj"])
        r.neoporezivi_prijevoz = inp.prijevoz  # Do visine javnog prijevoza
        r.neoporezivi_regres = inp.regres
        r.ukupno_neoporezivi = round(
            r.neoporezivi_prehrana + r.neoporezivi_prijevoz + r.neoporezivi_regres, 2
        )

        # 10. Za isplatu
        r.za_isplatu = round(r.neto + r.ukupno_neoporezivi, 2)

        # 11. Doprinosi na plaću (teret poslodavca)
        r.zdravstveno = round(r.bruto_ukupno * ZDRAVSTVENO_STOPA, 2)

        # 12. Ukupni trošak poslodavca
        r.trosak_poslodavca = round(
            r.bruto_ukupno + r.zdravstveno + r.ukupno_neoporezivi, 2
        )

        # 13. JOPPD
        r.joppd_mio_i = r.mio_i
        r.joppd_mio_ii = r.mio_ii
        r.joppd_zdravstveno = r.zdravstveno
        r.joppd_dohodak = r.dohodak
        r.joppd_porez = r.porez
        r.joppd_prirez = r.prirez

        # Detalji
        r.detalji = {
            "grad": inp.grad,
            "prirez_stopa": f"{r.prirez_stopa * 100:.0f}%",
            "osobni_odbitak_baza": OSOBNI_ODBITAK_BAZA,
            "uzdrzavanih": len(inp.uzdrzavani),
            "porez_stopa": "20%" if r.porezna_osnovica <= POREZ_GRANICA_MJ else "20%+30%",
        }

        return r

    def bruto_iz_neto(
        self, zeljeni_neto: float, grad: str = "zagreb",
        uzdrzavani: Optional[List[UzdrzavaniClan]] = None,
    ) -> ObracunPlaceResult:
        """Izračunaj bruto iz željenog neta (iterativno)."""
        # Newton-Raphson iteracija
        bruto = zeljeni_neto * 1.5  # Početna procjena
        for _ in range(50):
            inp = ObracunPlaceInput(
                bruto=bruto, grad=grad,
                uzdrzavani=uzdrzavani or [],
            )
            r = self.obracun(inp)
            diff = r.neto - zeljeni_neto

            if abs(diff) < 0.01:
                return r

            # Adjust bruto
            bruto -= diff * 0.8

        # Return best approximation
        return self.obracun(ObracunPlaceInput(
            bruto=bruto, grad=grad,
            uzdrzavani=uzdrzavani or [],
        ))

    def minimalna_placa(self, grad: str = "zagreb") -> ObracunPlaceResult:
        """Obračunaj minimalnu plaću za 2026."""
        return self.obracun(ObracunPlaceInput(bruto=1050.00, grad=grad))

    def to_joppd_dict(self, result: ObracunPlaceResult, oib_radnik: str,
                       ime_prezime: str, oznaka_stjecatelja: str = "0001"
                       ) -> Dict[str, Any]:
        """Generiraj JOPPD Stranu B podatke za jednog radnika."""
        return {
            "oib": oib_radnik,
            "ime_prezime": ime_prezime,
            "oznaka_stjecatelja": oznaka_stjecatelja,
            "bruto": result.bruto_ukupno,
            "mio_i": result.joppd_mio_i,
            "mio_ii": result.joppd_mio_ii,
            "dohodak": result.joppd_dohodak,
            "osobni_odbitak": result.osobni_odbitak,
            "porezna_osnovica": result.porezna_osnovica,
            "porez": result.joppd_porez,
            "prirez": result.joppd_prirez,
            "neto": result.neto,
            "neoporezivo": result.ukupno_neoporezivi,
            "za_isplatu": result.za_isplatu,
            "zdravstveno_poslodavac": result.joppd_zdravstveno,
            "ukupni_trosak": result.trosak_poslodavca,
        }
