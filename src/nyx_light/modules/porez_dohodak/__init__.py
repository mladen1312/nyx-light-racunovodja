"""
Nyx Light — Modul C: DOH Obrazac (Prijava poreza na dohodak)

Za obrtnike, slobodna zanimanja, paušaliste, dohodak od imovine itd.
Rok predaje: 28. veljače za prethodnu godinu.

Stope poreza na dohodak:
- 20% do 50.400 EUR godišnje (4.200 EUR/mj × 12)
- 30% iznad 50.400 EUR godišnje

Osobni odbitak: 560 EUR/mj × 12 = 6.720 EUR godišnje (osnovni)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.porez_dohodak")

DOH_STOPA_NIZA = 20.0     # %
DOH_STOPA_VISA = 30.0     # %
DOH_PRAG_GODISNJI = 50_400.0  # EUR godišnje (4.200 × 12)
OSOBNI_ODBITAK_MJESECNI = 560.0
OSOBNI_ODBITAK_GODISNJI = 6_720.0  # 560 × 12

# Paušalni obrt — pragovi i stope
PAUSALNI_PRAG_PRIHODA = 39_816.84  # EUR godišnje (300.000 HRK equivalent)
PAUSALNI_STOPA = 10.0  # % na paušalnu osnovicu

# Koeficijenti za djecu (isti kao za plaće)
KOEF_DJECA = [0.7, 1.0, 1.4, 1.9, 2.5, 3.2, 4.0, 4.9, 5.9]


@dataclass
class DOHObrazac:
    """Prijava poreza na dohodak."""
    godina: int = 0
    oib: str = ""
    ime_prezime: str = ""
    vrsta: str = "obrt"  # obrt, slobodno_zanimanje, pausalni_obrt, imovina

    # Primitci i izdatci
    ukupni_primitci: float = 0.0
    ukupni_izdatci: float = 0.0
    dohodak: float = 0.0

    # Osobni odbitak
    osnovni_odbitak: float = OSOBNI_ODBITAK_GODISNJI
    djeca_odbitak: float = 0.0
    uzdrzavani_odbitak: float = 0.0
    invalidnost_odbitak: float = 0.0
    ukupni_odbitak: float = 0.0

    # Porez
    porezna_osnovica: float = 0.0
    porez_niza_stopa: float = 0.0   # 20%
    porez_visa_stopa: float = 0.0   # 30%
    ukupni_porez: float = 0.0
    prirez: float = 0.0
    prirez_stopa: float = 0.0
    ukupno_porez_prirez: float = 0.0

    # Olakšica mladi
    olaksica_mladi_pct: float = 0.0
    olaksica_mladi_iznos: float = 0.0

    # Predujmovi
    placeni_predujmovi: float = 0.0
    razlika_za_uplatu: float = 0.0
    razlika_za_povrat: float = 0.0

    # Doprinosi (za obrtnike)
    mio_1_godisnje: float = 0.0
    mio_2_godisnje: float = 0.0
    zdravstveno_godisnje: float = 0.0


class PorezDohodakEngine:
    """Priprema DOH obrasca."""

    def __init__(self):
        self._count = 0

    def calculate_obrt(
        self,
        godina: int,
        ukupni_primitci: float,
        ukupni_izdatci: float,
        djeca: int = 0,
        uzdrzavani: int = 0,
        grad: str = "Zagreb",
        prirez_stopa: float = 0.0,
        placeni_predujmovi: float = 0.0,
        oib: str = "",
        ime: str = "",
        dob: int = 35,
    ) -> DOHObrazac:
        """Izračunaj porez na dohodak za obrtnika."""
        doh = DOHObrazac(
            godina=godina, oib=oib, ime_prezime=ime, vrsta="obrt",
            ukupni_primitci=ukupni_primitci, ukupni_izdatci=ukupni_izdatci,
            placeni_predujmovi=placeni_predujmovi,
        )

        # Dohodak = primitci - izdatci
        doh.dohodak = max(0, round(ukupni_primitci - ukupni_izdatci, 2))

        # Osobni odbitak
        doh.osnovni_odbitak = OSOBNI_ODBITAK_GODISNJI
        if djeca > 0:
            for i in range(min(djeca, len(KOEF_DJECA))):
                doh.djeca_odbitak += round(KOEF_DJECA[i] * OSOBNI_ODBITAK_GODISNJI, 2)
        doh.uzdrzavani_odbitak = round(uzdrzavani * 0.7 * OSOBNI_ODBITAK_GODISNJI, 2)
        doh.ukupni_odbitak = round(
            doh.osnovni_odbitak + doh.djeca_odbitak + doh.uzdrzavani_odbitak +
            doh.invalidnost_odbitak, 2
        )

        # Porezna osnovica
        doh.porezna_osnovica = max(0, round(doh.dohodak - doh.ukupni_odbitak, 2))

        # Porez — progresivne stope
        if doh.porezna_osnovica <= DOH_PRAG_GODISNJI:
            doh.porez_niza_stopa = round(doh.porezna_osnovica * DOH_STOPA_NIZA / 100, 2)
        else:
            doh.porez_niza_stopa = round(DOH_PRAG_GODISNJI * DOH_STOPA_NIZA / 100, 2)
            doh.porez_visa_stopa = round(
                (doh.porezna_osnovica - DOH_PRAG_GODISNJI) * DOH_STOPA_VISA / 100, 2
            )
        doh.ukupni_porez = round(doh.porez_niza_stopa + doh.porez_visa_stopa, 2)

        # Prirez
        doh.prirez_stopa = prirez_stopa or self._get_prirez(grad)
        doh.prirez = round(doh.ukupni_porez * doh.prirez_stopa / 100, 2)
        doh.ukupno_porez_prirez = round(doh.ukupni_porez + doh.prirez, 2)

        # Olakšica za mlade
        if dob < 25:
            doh.olaksica_mladi_pct = 100.0
        elif dob < 30:
            doh.olaksica_mladi_pct = 50.0
        if doh.olaksica_mladi_pct > 0:
            doh.olaksica_mladi_iznos = round(
                doh.ukupno_porez_prirez * doh.olaksica_mladi_pct / 100, 2
            )
            doh.ukupno_porez_prirez = round(
                doh.ukupno_porez_prirez - doh.olaksica_mladi_iznos, 2
            )

        # Razlika
        razlika = round(doh.ukupno_porez_prirez - placeni_predujmovi, 2)
        if razlika > 0:
            doh.razlika_za_uplatu = razlika
        else:
            doh.razlika_za_povrat = abs(razlika)

        # Doprinosi za obrtnika (referentno)
        doh.mio_1_godisnje = round(doh.dohodak * 0.15, 2)
        doh.mio_2_godisnje = round(doh.dohodak * 0.05, 2)
        doh.zdravstveno_godisnje = round(doh.dohodak * 0.165, 2)

        self._count += 1
        return doh

    def calculate_pausalni(
        self,
        godina: int,
        godisnji_prihod: float,
        oib: str = "",
        ime: str = "",
    ) -> Dict[str, Any]:
        """Izračunaj porez za paušalnog obrtnika."""
        if godisnji_prihod > PAUSALNI_PRAG_PRIHODA:
            return {
                "error": True,
                "message": (
                    f"Godišnji prihod ({godisnji_prihod:.2f} EUR) prelazi prag "
                    f"za paušalno oporezivanje ({PAUSALNI_PRAG_PRIHODA:.2f} EUR). "
                    "Obveznik mora prijeći na vođenje poslovnih knjiga."
                ),
            }

        # Paušalna osnovica = 50% prihoda (ali min po razredima)
        if godisnji_prihod <= 11_277.64:
            pausalna_osnovica = 1_692.00  # Fiksno za najniži razred
        elif godisnji_prihod <= 17_784.42:
            pausalna_osnovica = 2_658.00
        elif godisnji_prihod <= 26_544.56:
            pausalna_osnovica = 3_978.00
        else:
            pausalna_osnovica = 5_298.00  # Najviši razred

        porez = round(pausalna_osnovica * PAUSALNI_STOPA / 100, 2)
        prirez = round(porez * 0.18, 2)  # Default Zagreb

        self._count += 1
        return {
            "godina": godina,
            "vrsta": "pausalni_obrt",
            "godisnji_prihod": godisnji_prihod,
            "pausalna_osnovica": pausalna_osnovica,
            "porez": porez,
            "prirez": prirez,
            "ukupno": round(porez + prirez, 2),
            "tromjesecni_predujam": round((porez + prirez) / 4, 2),
            "rok_predaje_kpr": "15. u mjesecu nakon kvartala",
            "requires_approval": True,
        }

    def to_dict(self, doh: DOHObrazac) -> Dict[str, Any]:
        return {
            "obrazac": "DOH",
            "godina": doh.godina,
            "oib": doh.oib,
            "ime": doh.ime_prezime,
            "vrsta": doh.vrsta,
            "primitci": doh.ukupni_primitci,
            "izdatci": doh.ukupni_izdatci,
            "dohodak": doh.dohodak,
            "osobni_odbitak": doh.ukupni_odbitak,
            "porezna_osnovica": doh.porezna_osnovica,
            "porez": doh.ukupni_porez,
            "prirez": doh.prirez,
            "ukupno_porez_prirez": doh.ukupno_porez_prirez,
            "predujmovi": doh.placeni_predujmovi,
            "za_uplatu": doh.razlika_za_uplatu,
            "za_povrat": doh.razlika_za_povrat,
            "rok_predaje": f"28.02.{doh.godina + 1}",
            "platforma": "ePorezna",
            "requires_approval": True,
        }

    def _get_prirez(self, grad: str) -> float:
        prirez_map = {
            "zagreb": 18.0, "split": 15.0, "rijeka": 14.0,
            "osijek": 13.0, "zadar": 12.0, "dubrovnik": 10.0,
            "varaždin": 10.0, "pula": 15.0, "karlovac": 12.0,
        }
        return prirez_map.get(grad.lower(), 0.0)

    def get_stats(self):
        return {"doh_generated": self._count}
