"""
Nyx Light — Modul D: GFI Priprema (Godišnji financijski izvještaji)

Priprema podataka za predaju GFI-POD u FINA-u:
- Bilanca (BIL obrazac)
- Račun dobiti i gubitka (RDG obrazac)
- Checklist zaključnih knjiženja
- Rokovi i kategorizacija poduzetnika

NAPOMENA: Ovo je PRIPREMA — konačne iznose potvrđuje računovođa.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.gfi_prep")


@dataclass
class GFIChecklistItem:
    name: str
    done: bool = False
    notes: str = ""
    priority: str = "normal"  # critical, high, normal


# Rokovi prema kategoriji poduzetnika
ROKOVI_GFI = {
    "mikro": {"rok": "30. travnja", "revizija": False},
    "mali": {"rok": "30. travnja", "revizija": False},
    "srednji": {"rok": "30. travnja", "revizija": True},
    "veliki": {"rok": "30. lipnja", "revizija": True},
}

# Pragovi za kategorizaciju (Zakon o računovodstvu čl. 5.)
KATEGORIJE_PODUZETNIKA = {
    "mikro": {"aktiva_max": 350_000, "prihod_max": 700_000, "zaposlenici_max": 10},
    "mali": {"aktiva_max": 2_000_000, "prihod_max": 4_000_000, "zaposlenici_max": 50},
    "srednji": {"aktiva_max": 20_000_000, "prihod_max": 40_000_000, "zaposlenici_max": 250},
    # Sve iznad = veliki
}


class GFIPrepEngine:
    """Priprema godišnjih financijskih izvještaja."""

    def __init__(self):
        self._prep_count = 0

    def kategorija_poduzetnika(
        self, aktiva: float, prihod: float, zaposlenici: int
    ) -> Dict[str, Any]:
        """Odredi kategoriju poduzetnika prema Zakonu o računovodstvu."""
        # Dva od tri kriterija moraju biti ispunjena
        for kat, pragovi in KATEGORIJE_PODUZETNIKA.items():
            uvjeti = 0
            if aktiva <= pragovi["aktiva_max"]:
                uvjeti += 1
            if prihod <= pragovi["prihod_max"]:
                uvjeti += 1
            if zaposlenici <= pragovi["zaposlenici_max"]:
                uvjeti += 1
            if uvjeti >= 2:
                rok_info = ROKOVI_GFI[kat]
                return {
                    "kategorija": kat,
                    "rok_predaje": rok_info["rok"],
                    "revizijska_obveza": rok_info["revizija"],
                    "standardi": "HSFI" if kat in ("mikro", "mali") else "MSFI (opcija HSFI)",
                    "biljeske_obvezne": kat != "mikro",
                    "novčani_tok_obvezan": kat in ("srednji", "veliki"),
                }
        return {
            "kategorija": "veliki",
            "rok_predaje": "30. lipnja",
            "revizijska_obveza": True,
            "standardi": "MSFI",
            "biljeske_obvezne": True,
            "novčani_tok_obvezan": True,
        }

    def bilanca_struktura(self) -> Dict[str, Any]:
        """Vrati strukturu BIL obrasca za popunjavanje."""
        return {
            "naziv": "BILANCA (BIL obrazac)",
            "aktiva": {
                "A": {"naziv": "POTRAŽIVANJA ZA UPISANI A NEUPLAĆENI KAPITAL", "aop": "001"},
                "B": {
                    "naziv": "DUGOTRAJNA IMOVINA",
                    "aop": "002",
                    "stavke": {
                        "I": {"naziv": "Nematerijalna imovina", "aop": "003",
                              "konta": ["0100-0190"]},
                        "II": {"naziv": "Materijalna imovina", "aop": "008",
                               "konta": ["0200-0290"]},
                        "III": {"naziv": "Dugotrajna financijska imovina", "aop": "018",
                                "konta": ["0300-0400"]},
                        "IV": {"naziv": "Potraživanja", "aop": "024", "konta": ["0320"]},
                    },
                },
                "C": {
                    "naziv": "KRATKOTRAJNA IMOVINA",
                    "aop": "029",
                    "stavke": {
                        "I": {"naziv": "Zalihe", "aop": "030", "konta": ["1000-1100"]},
                        "II": {"naziv": "Potraživanja", "aop": "036", "konta": ["1200-1250"]},
                        "III": {"naziv": "Kratkotrajna financijska imovina", "aop": "043",
                                "konta": ["1300-1310"]},
                        "IV": {"naziv": "Novac u banci i blagajni", "aop": "048",
                               "konta": ["1400-1520"]},
                    },
                },
                "D": {"naziv": "PLAĆENI TROŠKOVI BUDUĆEG RAZDOBLJA", "aop": "050",
                       "konta": ["1600-1900"]},
                "E": {"naziv": "UKUPNO AKTIVA", "aop": "051"},
            },
            "pasiva": {
                "A": {
                    "naziv": "KAPITAL I REZERVE",
                    "aop": "052",
                    "stavke": {
                        "I": {"naziv": "Temeljni kapital", "aop": "053", "konta": ["2000-2010"]},
                        "II": {"naziv": "Kapitalne rezerve", "aop": "055", "konta": ["2100"]},
                        "III": {"naziv": "Rezerve iz dobiti", "aop": "058", "konta": ["2200-2220"]},
                        "IV": {"naziv": "Revalorizacijske rezerve", "aop": "062",
                               "konta": ["2300"]},
                        "V": {"naziv": "Zadržana dobit/preneseni gubitak", "aop": "065",
                              "konta": ["2400-2410"]},
                        "VI": {"naziv": "Dobit/gubitak poslovne godine", "aop": "068",
                               "konta": ["2500-2510"]},
                    },
                },
                "B": {"naziv": "REZERVIRANJA", "aop": "073", "konta": ["3200-3230"]},
                "C": {"naziv": "DUGOROČNE OBVEZE", "aop": "078", "konta": ["3000-3400"]},
                "D": {"naziv": "KRATKOROČNE OBVEZE", "aop": "088", "konta": ["4000-4520"]},
                "E": {"naziv": "ODGOĐENO PLAĆANJE TROŠKOVA", "aop": "098",
                       "konta": ["4500-4520"]},
                "F": {"naziv": "UKUPNO PASIVA", "aop": "099"},
            },
            "note": "Aktiva (AOP 051) MORA biti jednaka Pasivi (AOP 099)",
        }

    def rdg_struktura(self) -> Dict[str, Any]:
        """Vrati strukturu RDG obrasca."""
        return {
            "naziv": "RAČUN DOBITI I GUBITKA (RDG obrazac)",
            "stavke": {
                "I": {"naziv": "POSLOVNI PRIHODI", "aop": "101",
                      "konta": ["6000-6400"]},
                "II": {"naziv": "POSLOVNI RASHODI", "aop": "109",
                       "konta": ["5000-5900", "7000-7400"]},
                "III": {"naziv": "FINANCIJSKI PRIHODI", "aop": "124",
                        "konta": ["6200-6210"]},
                "IV": {"naziv": "FINANCIJSKI RASHODI", "aop": "129",
                       "konta": ["7600-7620"]},
                "V": {"naziv": "UKUPNI PRIHODI (I+III)", "aop": "135"},
                "VI": {"naziv": "UKUPNI RASHODI (II+IV)", "aop": "136"},
                "VII": {"naziv": "DOBIT/GUBITAK PRIJE OPOREZIVANJA", "aop": "137"},
                "VIII": {"naziv": "POREZ NA DOBIT", "aop": "140",
                         "konta": ["8300"]},
                "IX": {"naziv": "DOBIT/GUBITAK RAZDOBLJA", "aop": "141"},
            },
        }

    def zakljucna_knjizenja_checklist(self, godina: int) -> Dict[str, Any]:
        """Checklist zaključnih knjiženja za godinu."""
        items = [
            GFIChecklistItem("Usklađivanje zaliha s inventurom", priority="critical",
                             notes="Fizički popis na 31.12."),
            GFIChecklistItem("Godišnji obračun amortizacije", priority="critical"),
            GFIChecklistItem("Revalorizacija deviznih stavki (tečaj HNB 31.12.)", priority="high"),
            GFIChecklistItem("Ispravak vrijednosti potraživanja (starija od 60 dana)",
                             priority="high", notes="Čl. 9. Zakona o porezu na dobit"),
            GFIChecklistItem("Provjera rezerviranja", priority="high"),
            GFIChecklistItem("Razgraničenja — ukidanje isteklih", priority="high"),
            GFIChecklistItem("Porezno nepriznati rashodi — korekcija", priority="critical",
                             notes="Reprezentacija 50%, kazne, privatna upotreba"),
            GFIChecklistItem("Obračun poreza na dobit", priority="critical"),
            GFIChecklistItem("Zatvaranje razreda 5/6 (troškovi/prihodi)", priority="critical"),
            GFIChecklistItem("Provjera ravnoteže aktiva = pasiva", priority="critical"),
            GFIChecklistItem("Priprema bilješki uz financijske izvještaje", priority="high"),
            GFIChecklistItem("Provjera usklađenosti IOS-a s partnerima", priority="normal"),
            GFIChecklistItem("Provjera obveze revizije", priority="high"),
        ]

        self._prep_count += 1

        return {
            "godina": godina,
            "total_items": len(items),
            "critical": sum(1 for i in items if i.priority == "critical"),
            "items": [
                {"name": i.name, "done": i.done, "notes": i.notes, "priority": i.priority}
                for i in items
            ],
            "rok_gfi_standardni": "30. travnja",
            "rok_gfi_revizija": "30. lipnja",
        }

    def get_stats(self) -> Dict[str, Any]:
        return {"preparations": self._prep_count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Kontrolni zbrojevi, AOP pozicije, validacija
# ════════════════════════════════════════════════════════

from decimal import Decimal, ROUND_HALF_UP

def _d(val) -> Decimal:
    return Decimal(str(val) if val else '0')

def _r2(val) -> float:
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# AOP pozicije za bilancu (GFI-POD)
AOP_BILANCA = {
    # AKTIVA
    "001": "Dugotrajna imovina",
    "002": "Nematerijalna imovina",
    "003": "Materijalna imovina",
    "008": "Financijska imovina",
    "015": "Kratkotrajna imovina",
    "016": "Zalihe",
    "020": "Potraživanja",
    "030": "Financijska imovina (kratkotrajna)",
    "036": "Novac u banci i blagajni",
    "040": "Plaćeni troškovi budućeg razdoblja",
    "041": "UKUPNA AKTIVA",
    # PASIVA
    "042": "Kapital i rezerve",
    "043": "Temeljni kapital",
    "050": "Rezerve",
    "060": "Zadržana dobit/preneseni gubitak",
    "064": "Dobit/gubitak tekuće godine",
    "068": "Dugoročne obveze",
    "080": "Kratkoročne obveze",
    "090": "Odgođeno plaćanje troškova",
    "091": "UKUPNA PASIVA",
}

# AOP pozicije za RDG (Račun dobiti i gubitka)
AOP_RDG = {
    "100": "Poslovni prihodi",
    "101": "Prihodi od prodaje",
    "109": "Poslovni rashodi",
    "110": "Materijalni troškovi",
    "113": "Troškovi osoblja",
    "119": "Amortizacija",
    "125": "Ostali troškovi",
    "130": "Financijski prihodi",
    "131": "Financijski rashodi",
    "140": "Ukupni prihodi",
    "141": "Ukupni rashodi",
    "145": "Dobit/gubitak prije poreza",
    "146": "Porez na dobit",
    "150": "Dobit/gubitak razdoblja",
}


class GFIValidator:
    """Validacija financijskih izvještaja prema HSFI."""

    @staticmethod
    def validate_bilanca(data: dict) -> List[dict]:
        """Provjeri da aktiva = pasiva i ostale kontrole."""
        errors = []

        aktiva = _d(data.get("ukupna_aktiva", data.get("041", 0)))
        pasiva = _d(data.get("ukupna_pasiva", data.get("091", 0)))

        # Kontrola 1: Aktiva = Pasiva
        if abs(aktiva - pasiva) > _d("0.01"):
            errors.append({
                "check": "aktiva_pasiva",
                "msg": f"Aktiva ({aktiva}) ≠ Pasiva ({pasiva}), razlika: {aktiva - pasiva}",
                "severity": "error",
            })

        # Kontrola 2: Ukupna aktiva = dugotrajna + kratkotrajna + AVR
        dugotrajna = _d(data.get("001", 0))
        kratkotrajna = _d(data.get("015", 0))
        avr = _d(data.get("040", 0))
        calc_aktiva = dugotrajna + kratkotrajna + avr
        if abs(aktiva - calc_aktiva) > _d("0.01") and aktiva > 0:
            errors.append({
                "check": "aktiva_sastavnice",
                "msg": f"Aktiva ({aktiva}) ≠ DI({dugotrajna})+KI({kratkotrajna})+AVR({avr})={calc_aktiva}",
                "severity": "warning",
            })

        # Kontrola 3: Pasiva = kapital + dugoročne + kratkoročne + PVR
        kapital = _d(data.get("042", 0))
        dugorocne = _d(data.get("068", 0))
        kratkorocne = _d(data.get("080", 0))
        pvr = _d(data.get("090", 0))
        calc_pasiva = kapital + dugorocne + kratkorocne + pvr
        if abs(pasiva - calc_pasiva) > _d("0.01") and pasiva > 0:
            errors.append({
                "check": "pasiva_sastavnice",
                "msg": f"Pasiva ({pasiva}) ≠ K({kapital})+DO({dugorocne})+KO({kratkorocne})+PVR({pvr})={calc_pasiva}",
                "severity": "warning",
            })

        # Kontrola 4: Dobit u bilanci = dobit u RDG
        dobit_bilanca = _d(data.get("064", 0))
        dobit_rdg = _d(data.get("150", data.get("rdg_dobit", 0)))
        if abs(dobit_bilanca - dobit_rdg) > _d("0.01") and dobit_rdg != 0:
            errors.append({
                "check": "dobit_konzistencija",
                "msg": f"Dobit u bilanci ({dobit_bilanca}) ≠ dobit u RDG ({dobit_rdg})",
                "severity": "error",
            })

        return errors

    @staticmethod
    def validate_rdg(data: dict) -> List[dict]:
        """Kontrola RDG-a."""
        errors = []

        prihodi = _d(data.get("140", 0))
        rashodi = _d(data.get("141", 0))
        dobit = _d(data.get("145", 0))

        if abs(dobit - (prihodi - rashodi)) > _d("0.01") and prihodi > 0:
            errors.append({
                "check": "rdg_dobit",
                "msg": f"Dobit ({dobit}) ≠ Prihodi({prihodi}) - Rashodi({rashodi}) = {prihodi-rashodi}",
                "severity": "error",
            })

        porez = _d(data.get("146", 0))
        neto = _d(data.get("150", 0))
        if abs(neto - (dobit - porez)) > _d("0.01") and dobit > 0:
            errors.append({
                "check": "rdg_neto",
                "msg": f"Neto dobit ({neto}) ≠ Dobit({dobit}) - Porez({porez}) = {dobit-porez}",
                "severity": "error",
            })

        return errors
