"""
Nyx Light — Modul G3: Likvidacijsko računovodstvo

Podrška za postupak dobrovoljne likvidacije d.o.o./j.d.o.o./d.d.
Checklist koraka, obrasci, rokovi, knjiženja.

Postupak:
1. Odluka o likvidaciji (skupština)
2. Upis u sudski registar + imenovanje likvidatora
3. Poziv vjerovnicima (rok min. 6 mjeseci, NN objava)
4. Likvidacijski financijski izvještaji
5. Podmirenje obveza, prodaja imovine, naplata potraživanja
6. Završni likvidacijski izvještaj
7. Podjela preostale imovine članovima
8. Brisanje iz sudskog registra

Referenca: Zakon o trgovačkim društvima (čl. 369.-381.)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.likvidacija")


@dataclass
class LikvidacijaStatus:
    """Praćenje faze likvidacije."""
    klijent_id: str = ""
    naziv: str = ""
    oib: str = ""
    datum_odluke: str = ""
    likvidator: str = ""
    faza: str = "priprema"  # priprema, registracija, vjerovnici, izvjestaji, zavrsna
    checklist: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class LikvidacijaEngine:
    """Podrška za likvidacijski postupak."""

    def __init__(self):
        self._active: Dict[str, LikvidacijaStatus] = {}

    def start(self, klijent_id: str, naziv: str, oib: str,
              datum_odluke: str, likvidator: str) -> LikvidacijaStatus:
        """Pokreni likvidacijski postupak."""
        status = LikvidacijaStatus(
            klijent_id=klijent_id, naziv=naziv, oib=oib,
            datum_odluke=datum_odluke, likvidator=likvidator,
            faza="priprema",
        )
        status.checklist = self._full_checklist()
        self._active[klijent_id] = status
        return status

    def get_status(self, klijent_id: str) -> LikvidacijaStatus:
        return self._active.get(klijent_id)

    def advance_phase(self, klijent_id: str, nova_faza: str) -> Dict:
        status = self._active.get(klijent_id)
        if not status:
            return {"success": False, "error": "Klijent nije u likvidaciji"}

        faze = ["priprema", "registracija", "vjerovnici", "izvjestaji", "zavrsna"]
        if nova_faza not in faze:
            return {"success": False, "error": f"Nepoznata faza: {nova_faza}"}

        status.faza = nova_faza
        return {"success": True, "faza": nova_faza}

    def _full_checklist(self) -> List[Dict]:
        return [
            # Faza 1: Priprema
            {"faza": "priprema", "korak": 1, "done": False, "priority": "critical",
             "opis": "Odluka skupštine o prestanku društva i likvidaciji",
             "zakon": "čl. 369. ZTD"},
            {"faza": "priprema", "korak": 2, "done": False, "priority": "critical",
             "opis": "Imenovanje likvidatora (može biti član uprave ili treća osoba)",
             "zakon": "čl. 371. ZTD"},
            {"faza": "priprema", "korak": 3, "done": False, "priority": "high",
             "opis": "Izrada otvorene bilance na datum odluke o likvidaciji",
             "zakon": "čl. 374. ZTD"},

            # Faza 2: Registracija
            {"faza": "registracija", "korak": 4, "done": False, "priority": "critical",
             "opis": "Prijava upisa likvidacije u sudski registar",
             "zakon": "čl. 370. ZTD"},
            {"faza": "registracija", "korak": 5, "done": False, "priority": "critical",
             "opis": "Objava poziva vjerovnicima u Narodnim novinama",
             "zakon": "čl. 373. ZTD — rok za prijavu: min. 6 mjeseci"},
            {"faza": "registracija", "korak": 6, "done": False, "priority": "high",
             "opis": "Obavijest Poreznoj upravi o pokretanju likvidacije",
             "zakon": "Opći porezni zakon"},
            {"faza": "registracija", "korak": 7, "done": False, "priority": "high",
             "opis": "Promjena naziva: dodati 'u likvidaciji' (npr. Firma d.o.o. u likvidaciji)",
             "zakon": "čl. 370. st. 2. ZTD"},

            # Faza 3: Vjerovnici i imovina
            {"faza": "vjerovnici", "korak": 8, "done": False, "priority": "critical",
             "opis": "Naplata svih potraživanja (tužbe ako potrebno)",
             "zakon": "čl. 372. ZTD"},
            {"faza": "vjerovnici", "korak": 9, "done": False, "priority": "critical",
             "opis": "Podmirenje svih obveza prema vjerovnicima",
             "zakon": "čl. 372. ZTD"},
            {"faza": "vjerovnici", "korak": 10, "done": False, "priority": "high",
             "opis": "Prodaja imovine (osnovna sredstva, zalihe)",
             "zakon": "čl. 372. ZTD"},
            {"faza": "vjerovnici", "korak": 11, "done": False, "priority": "high",
             "opis": "Raskid ugovora o radu sa zaposlenicima (otkazni rokovi!)",
             "zakon": "Zakon o radu"},
            {"faza": "vjerovnici", "korak": 12, "done": False, "priority": "normal",
             "opis": "Deregistracija PDV obveznika (ako primjenjivo)",
             "zakon": "čl. 81. Zakon o PDV-u"},

            # Faza 4: Financijski izvještaji
            {"faza": "izvjestaji", "korak": 13, "done": False, "priority": "critical",
             "opis": "Izrada završnog likvidacijskog izvještaja (bilanca + RDG)",
             "zakon": "čl. 374. st. 2. ZTD"},
            {"faza": "izvjestaji", "korak": 14, "done": False, "priority": "critical",
             "opis": "Predaja porezne prijave (PD obrazac za skraćeno razdoblje)",
             "zakon": "Zakon o porezu na dobit"},
            {"faza": "izvjestaji", "korak": 15, "done": False, "priority": "high",
             "opis": "Predaja GFI na FINA RGFI za likvidacijsko razdoblje",
             "zakon": "Zakon o računovodstvu"},
            {"faza": "izvjestaji", "korak": 16, "done": False, "priority": "high",
             "opis": "Revizija završnog izvještaja (ako je društvo obveznik revizije)",
             "zakon": "Zakon o reviziji"},

            # Faza 5: Završna
            {"faza": "zavrsna", "korak": 17, "done": False, "priority": "critical",
             "opis": "Podjela preostale imovine članovima (prema udjelima)",
             "zakon": "čl. 375. ZTD"},
            {"faza": "zavrsna", "korak": 18, "done": False, "priority": "critical",
             "opis": "Prijava brisanja društva iz sudskog registra",
             "zakon": "čl. 376. ZTD"},
            {"faza": "zavrsna", "korak": 19, "done": False, "priority": "high",
             "opis": "Zatvaranje poslovnog računa u banci",
             "zakon": ""},
            {"faza": "zavrsna", "korak": 20, "done": False, "priority": "high",
             "opis": "Čuvanje poslovne dokumentacije (11 godina)",
             "zakon": "čl. 10. Zakon o računovodstvu"},
        ]

    def knjizenja_likvidacija(self) -> List[Dict]:
        """Tipična likvidacijska knjiženja."""
        return [
            {"opis": "Zatvaranje prihoda u dobit", "duguje": "7xxx", "potrazuje": "3900",
             "napomena": "Sve klase 7 → Dobit tekuće godine"},
            {"opis": "Zatvaranje rashoda u dobit", "duguje": "3900", "potrazuje": "5xxx/6xxx",
             "napomena": "Sve klase 5+6 → Dobit tekuće godine"},
            {"opis": "Prodaja imovine", "duguje": "1000/1200", "potrazuje": "0xxx",
             "napomena": "Primitak novca + otpis konta imovine"},
            {"opis": "Podmirenje obveza", "duguje": "4xxx", "potrazuje": "1000",
             "napomena": "Plaćanje svih dobavljača i dugova"},
            {"opis": "Isplata članova", "duguje": "3xxx", "potrazuje": "1000",
             "napomena": "Podjela preostale imovine"},
            {"opis": "Zatvaranje svih konta na nulu", "duguje": "—", "potrazuje": "—",
             "napomena": "Na kraju sva salda = 0"},
        ]

    def to_dict(self, status: LikvidacijaStatus) -> Dict[str, Any]:
        done = sum(1 for c in status.checklist if c["done"])
        total = len(status.checklist)
        return {
            "klijent": status.naziv,
            "oib": status.oib,
            "faza": status.faza,
            "likvidator": status.likvidator,
            "datum_odluke": status.datum_odluke,
            "progress": f"{done}/{total}",
            "progress_pct": round(done / total * 100, 1) if total else 0,
            "checklist": status.checklist,
            "tipicna_knjizenja": self.knjizenja_likvidacija(),
        }

    def get_stats(self):
        return {"active_liquidations": len(self._active)}
