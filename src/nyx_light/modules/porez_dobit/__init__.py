"""
Nyx Light — Modul C: PD Obrazac (Prijava poreza na dobit)

Priprema godišnje prijave poreza na dobit za predaju na ePorezna.
Rok: 30. travnja za prethodnu godinu.

Stopa poreza na dobit:
- 10% za prihode ≤ 1.000.000 EUR (čl. 28.a Zakona o porezu na dobit)
- 18% za prihode > 1.000.000 EUR

Porezna osnovica = Dobit prije oporezivanja
  + Porezno nepriznati rashodi (uvećanja)
  - Porezno priznate olakšice (umanjenja)
  = Porezna osnovica za PD

NAPOMENA: Konačne iznose potvrđuje računovođa.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.porez_dobit")

# Stope poreza na dobit (2026.)
PD_STOPA_NIZA = 10.0       # %
PD_STOPA_VISA = 18.0       # %
PD_PRAG_PRIHODA = 1_000_000.0  # EUR


@dataclass
class PDObrazac:
    """Prijava poreza na dobit."""
    godina: int = 0
    oib_obveznika: str = ""
    naziv_obveznika: str = ""

    # Iz RDG-a
    ukupni_prihodi: float = 0.0
    ukupni_rashodi: float = 0.0
    dobit_prije_oporezivanja: float = 0.0

    # Uvećanja porezne osnovice (porezno nepriznati rashodi)
    reprezentacija_nepriznata: float = 0.0    # 50% troškova reprezentacije
    kazne_i_penali: float = 0.0
    skrivene_isplate_dobiti: float = 0.0
    amortizacija_iznad_porezne: float = 0.0
    rashodi_za_osobne_potrebe: float = 0.0
    donacije_iznad_limita: float = 0.0        # >2% prihoda prethodne godine
    otpis_potraživanja_nepriznati: float = 0.0
    ostala_uvecanja: float = 0.0

    # Umanjenja porezne osnovice
    prihodi_od_dividendi: float = 0.0         # Već oporezovano
    reinvestirana_dobit: float = 0.0
    potpore_i_olaksice: float = 0.0
    prihodi_od_naplate_otpisa: float = 0.0    # Prethodno nepriznati otpisi
    ostala_umanjenja: float = 0.0

    # Izračun
    ukupna_uvecanja: float = 0.0
    ukupna_umanjenja: float = 0.0
    porezna_osnovica: float = 0.0
    stopa: float = 0.0
    porez_na_dobit: float = 0.0

    # Predujmovi
    placeni_predujmovi: float = 0.0
    razlika_za_uplatu: float = 0.0
    razlika_za_povrat: float = 0.0


class PorezDobitiEngine:
    """Priprema PD obrasca."""

    def __init__(self):
        self._count = 0

    def calculate(
        self,
        godina: int,
        ukupni_prihodi: float,
        ukupni_rashodi: float,
        uvecanja: Dict[str, float] = None,
        umanjenja: Dict[str, float] = None,
        placeni_predujmovi: float = 0.0,
        oib: str = "",
        naziv: str = "",
    ) -> PDObrazac:
        """Izračunaj porez na dobit."""
        pd = PDObrazac(
            godina=godina, oib_obveznika=oib, naziv_obveznika=naziv,
            ukupni_prihodi=ukupni_prihodi, ukupni_rashodi=ukupni_rashodi,
            dobit_prije_oporezivanja=round(ukupni_prihodi - ukupni_rashodi, 2),
            placeni_predujmovi=placeni_predujmovi,
        )

        # Uvećanja
        if uvecanja:
            pd.reprezentacija_nepriznata = uvecanja.get("reprezentacija_50pct", 0)
            pd.kazne_i_penali = uvecanja.get("kazne", 0)
            pd.skrivene_isplate_dobiti = uvecanja.get("skrivene_isplate", 0)
            pd.amortizacija_iznad_porezne = uvecanja.get("amortizacija_viska", 0)
            pd.rashodi_za_osobne_potrebe = uvecanja.get("osobne_potrebe", 0)
            pd.donacije_iznad_limita = uvecanja.get("donacije_viska", 0)
            pd.otpis_potraživanja_nepriznati = uvecanja.get("otpis_nepriznati", 0)
            pd.ostala_uvecanja = uvecanja.get("ostalo", 0)

        pd.ukupna_uvecanja = round(
            pd.reprezentacija_nepriznata + pd.kazne_i_penali +
            pd.skrivene_isplate_dobiti + pd.amortizacija_iznad_porezne +
            pd.rashodi_za_osobne_potrebe + pd.donacije_iznad_limita +
            pd.otpis_potraživanja_nepriznati + pd.ostala_uvecanja, 2
        )

        # Umanjenja
        if umanjenja:
            pd.prihodi_od_dividendi = umanjenja.get("dividende", 0)
            pd.reinvestirana_dobit = umanjenja.get("reinvestirana_dobit", 0)
            pd.potpore_i_olaksice = umanjenja.get("potpore", 0)
            pd.prihodi_od_naplate_otpisa = umanjenja.get("naplata_otpisa", 0)
            pd.ostala_umanjenja = umanjenja.get("ostalo", 0)

        pd.ukupna_umanjenja = round(
            pd.prihodi_od_dividendi + pd.reinvestirana_dobit +
            pd.potpore_i_olaksice + pd.prihodi_od_naplate_otpisa +
            pd.ostala_umanjenja, 2
        )

        # Porezna osnovica
        pd.porezna_osnovica = max(0, round(
            pd.dobit_prije_oporezivanja + pd.ukupna_uvecanja - pd.ukupna_umanjenja, 2
        ))

        # Stopa
        pd.stopa = PD_STOPA_NIZA if ukupni_prihodi <= PD_PRAG_PRIHODA else PD_STOPA_VISA
        pd.porez_na_dobit = round(pd.porezna_osnovica * pd.stopa / 100, 2)

        # Razlika
        razlika = round(pd.porez_na_dobit - placeni_predujmovi, 2)
        if razlika > 0:
            pd.razlika_za_uplatu = razlika
        else:
            pd.razlika_za_povrat = abs(razlika)

        self._count += 1
        return pd

    def checklist_uvecanja(self, troškovi: Dict[str, float] = None) -> List[Dict]:
        """Generiraj checklist porezno nepriznatih rashoda."""
        items = [
            {"stavka": "Reprezentacija (50%)", "zakon": "čl. 7. st. 1. t. 3. ZoPD",
             "opis": "50% troškova reprezentacije je porezno nepriznato",
             "auto_calc": True},
            {"stavka": "Kazne i penali", "zakon": "čl. 7. st. 1. t. 7. ZoPD",
             "opis": "Sve kazne, penali i zatezne kamate nisu porezno priznati",
             "auto_calc": False},
            {"stavka": "Amortizacija iznad porezne", "zakon": "čl. 12. ZoPD",
             "opis": "Amortizacija iznad porezno dopuštenih stopa",
             "auto_calc": True},
            {"stavka": "Darovi iznad 2% prihoda", "zakon": "čl. 7. st. 1. t. 8. ZoPD",
             "opis": "Donacije >2% prihoda prethodne godine",
             "auto_calc": True},
            {"stavka": "Otpis potraživanja", "zakon": "čl. 9. ZoPD",
             "opis": "Otpis potraživanja koji ne ispunjavaju uvjete čl. 9.",
             "auto_calc": False},
            {"stavka": "Rashodi za osobne potrebe", "zakon": "čl. 7. st. 1. t. 1. ZoPD",
             "opis": "Troškovi vlasnika koji nisu poslovni",
             "auto_calc": False},
            {"stavka": "Troškovi osobnih automobila iznad praga",
             "zakon": "čl. 7. st. 1. t. 4. ZoPD",
             "opis": "30% troškova korištenja osobnih automobila",
             "auto_calc": True},
            {"stavka": "Manjkovi iznad normi", "zakon": "čl. 7. st. 1. t. 5. ZoPD",
             "opis": "Manjkovi iznad visine utvrđene odlukom",
             "auto_calc": False},
        ]

        if troškovi:
            for item in items:
                if item["stavka"] == "Reprezentacija (50%)" and "reprezentacija" in troškovi:
                    item["iznos"] = round(troškovi["reprezentacija"] * 0.5, 2)

        return items

    def to_dict(self, pd: PDObrazac) -> Dict[str, Any]:
        return {
            "obrazac": "PD",
            "godina": pd.godina,
            "oib": pd.oib_obveznika,
            "naziv": pd.naziv_obveznika,
            "dobit_prije_oporezivanja": pd.dobit_prije_oporezivanja,
            "uvecanja": pd.ukupna_uvecanja,
            "umanjenja": pd.ukupna_umanjenja,
            "porezna_osnovica": pd.porezna_osnovica,
            "stopa": f"{pd.stopa}%",
            "porez_na_dobit": pd.porez_na_dobit,
            "predujmovi": pd.placeni_predujmovi,
            "za_uplatu": pd.razlika_za_uplatu,
            "za_povrat": pd.razlika_za_povrat,
            "rok_predaje": f"30.04.{pd.godina + 1}",
            "platforma": "ePorezna",
            "requires_approval": True,
        }

    def get_stats(self):
        return {"pd_generated": self._count}
