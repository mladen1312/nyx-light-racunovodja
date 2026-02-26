"""
Nyx Light — Modul C: PDV Prijava (PPO obrazac)

Priprema podataka za PDV prijavu na ePorezna:
- Izračun obveze/pretporeza
- Razvrstavanje po stopama (25%, 13%, 5%, 0%)
- EU transakcije (reverse charge, EC Sales List)
- Intrastat flagging
- Provjera rokova (20. u mjesecu)

NAPOMENA: Ovaj modul PRIPREMA podatke — predaju na ePorezna radi računovođa.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.pdv_prijava")


@dataclass
class PDVStavka:
    """Jedna PDV stavka (račun)."""
    tip: str = "ulazni"        # ulazni / izlazni
    broj_racuna: str = ""
    datum: str = ""
    oib_partnera: str = ""
    naziv_partnera: str = ""
    osnovica: float = 0.0
    pdv_stopa: float = 25.0
    pdv_iznos: float = 0.0
    ukupno: float = 0.0
    eu_transakcija: bool = False
    reverse_charge: bool = False
    zemlja: str = "HR"
    kategorija: str = ""       # roba / usluga


@dataclass
class PPOObrazac:
    """PDV prijava (PPO obrazac) za jedan period."""
    period: str = ""           # "2026-02" ili "2026-Q1"
    oib_obveznika: str = ""
    naziv_obveznika: str = ""
    mjesecna: bool = True      # True=mjesečna, False=tromjesečna

    # Izlazni PDV (obveza)
    izlazni_25_osnovica: float = 0.0
    izlazni_25_pdv: float = 0.0
    izlazni_13_osnovica: float = 0.0
    izlazni_13_pdv: float = 0.0
    izlazni_5_osnovica: float = 0.0
    izlazni_5_pdv: float = 0.0
    izlazni_0_osnovica: float = 0.0  # Oslobođeni

    # Ulazni PDV (pretporez)
    pretporez_25: float = 0.0
    pretporez_13: float = 0.0
    pretporez_5: float = 0.0

    # EU transakcije
    eu_stjecanja_osnovica: float = 0.0
    eu_stjecanja_pdv: float = 0.0
    eu_isporuke_osnovica: float = 0.0  # Za EC Sales List
    reverse_charge_primljeni: float = 0.0
    reverse_charge_izdani: float = 0.0

    # Rezultat
    ukupna_obveza: float = 0.0
    ukupni_pretporez: float = 0.0
    za_uplatu: float = 0.0          # Pozitivno = uplata državi
    za_povrat: float = 0.0          # Pozitivno = povrat od države

    # Stavke
    stavke_count: int = 0


class PDVPrijavaEngine:
    """Generira PDV prijavu iz knjiženih stavki."""

    def __init__(self):
        self._generation_count = 0

    def calculate(
        self,
        stavke: List[PDVStavka],
        oib_obveznika: str = "",
        naziv_obveznika: str = "",
        period: str = "",
        mjesecna: bool = True,
    ) -> PPOObrazac:
        """Izračunaj PDV prijavu iz liste stavki."""
        ppo = PPOObrazac(
            period=period or datetime.now().strftime("%Y-%m"),
            oib_obveznika=oib_obveznika,
            naziv_obveznika=naziv_obveznika,
            mjesecna=mjesecna,
            stavke_count=len(stavke),
        )

        for s in stavke:
            if s.tip == "izlazni":
                self._add_izlazni(ppo, s)
            elif s.tip == "ulazni":
                self._add_ulazni(ppo, s)

        # Izračunaj rezultat
        ppo.ukupna_obveza = round(
            ppo.izlazni_25_pdv + ppo.izlazni_13_pdv + ppo.izlazni_5_pdv +
            ppo.eu_stjecanja_pdv, 2
        )
        ppo.ukupni_pretporez = round(
            ppo.pretporez_25 + ppo.pretporez_13 + ppo.pretporez_5, 2
        )

        razlika = round(ppo.ukupna_obveza - ppo.ukupni_pretporez, 2)
        if razlika > 0:
            ppo.za_uplatu = razlika
        else:
            ppo.za_povrat = abs(razlika)

        self._generation_count += 1
        return ppo

    def _add_izlazni(self, ppo: PPOObrazac, s: PDVStavka):
        """Dodaj izlazni račun u PDV prijavu."""
        if s.eu_transakcija and s.reverse_charge:
            ppo.eu_isporuke_osnovica += s.osnovica
            ppo.reverse_charge_izdani += s.osnovica
            return

        if s.pdv_stopa == 25:
            ppo.izlazni_25_osnovica += s.osnovica
            ppo.izlazni_25_pdv += s.pdv_iznos
        elif s.pdv_stopa == 13:
            ppo.izlazni_13_osnovica += s.osnovica
            ppo.izlazni_13_pdv += s.pdv_iznos
        elif s.pdv_stopa == 5:
            ppo.izlazni_5_osnovica += s.osnovica
            ppo.izlazni_5_pdv += s.pdv_iznos
        else:
            ppo.izlazni_0_osnovica += s.osnovica

    def _add_ulazni(self, ppo: PPOObrazac, s: PDVStavka):
        """Dodaj ulazni račun (pretporez)."""
        if s.eu_transakcija:
            ppo.eu_stjecanja_osnovica += s.osnovica
            ppo.eu_stjecanja_pdv += s.pdv_iznos
            ppo.reverse_charge_primljeni += s.osnovica

        if s.pdv_stopa == 25:
            ppo.pretporez_25 += s.pdv_iznos
        elif s.pdv_stopa == 13:
            ppo.pretporez_13 += s.pdv_iznos
        elif s.pdv_stopa == 5:
            ppo.pretporez_5 += s.pdv_iznos

    def to_dict(self, ppo: PPOObrazac) -> Dict[str, Any]:
        """Pretvori u dict za pregled."""
        return {
            "period": ppo.period,
            "oib": ppo.oib_obveznika,
            "naziv": ppo.naziv_obveznika,
            "izlazni": {
                "25%": {"osnovica": ppo.izlazni_25_osnovica, "pdv": ppo.izlazni_25_pdv},
                "13%": {"osnovica": ppo.izlazni_13_osnovica, "pdv": ppo.izlazni_13_pdv},
                "5%":  {"osnovica": ppo.izlazni_5_osnovica, "pdv": ppo.izlazni_5_pdv},
                "0%":  {"osnovica": ppo.izlazni_0_osnovica},
            },
            "pretporez": {
                "25%": ppo.pretporez_25, "13%": ppo.pretporez_13, "5%": ppo.pretporez_5,
            },
            "eu": {
                "stjecanja": ppo.eu_stjecanja_osnovica,
                "isporuke": ppo.eu_isporuke_osnovica,
            },
            "ukupna_obveza": ppo.ukupna_obveza,
            "ukupni_pretporez": ppo.ukupni_pretporez,
            "za_uplatu": ppo.za_uplatu,
            "za_povrat": ppo.za_povrat,
            "stavke": ppo.stavke_count,
            "requires_approval": True,
            "note": "Predaja na ePorezna je odgovornost računovođe",
        }

    def ec_sales_list(self, stavke: List[PDVStavka]) -> List[Dict]:
        """Generiraj podatke za EC Sales List (zbirna prijava EU)."""
        eu_partners = {}
        for s in stavke:
            if s.eu_transakcija and s.tip == "izlazni":
                key = s.oib_partnera or s.naziv_partnera
                if key not in eu_partners:
                    eu_partners[key] = {
                        "oib": s.oib_partnera, "naziv": s.naziv_partnera,
                        "zemlja": s.zemlja, "roba": 0.0, "usluge": 0.0,
                    }
                if s.kategorija == "roba":
                    eu_partners[key]["roba"] += s.osnovica
                else:
                    eu_partners[key]["usluge"] += s.osnovica
        return list(eu_partners.values())

    def get_stats(self):
        return {"pdv_generated": self._generation_count}
