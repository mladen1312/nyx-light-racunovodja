"""
Nyx Light — Modul C6: Intrastat prijava

Statistička izvješća o robnoj razmjeni s državama EU.
Obveznici: poduzetnici koji prelaze prag za otpremu ili primitak robe.

Pragovi za 2026.:
- Primitak (uvoz iz EU): 400.000 EUR godišnje
- Otprema (izvoz u EU): 300.000 EUR godišnje

Rok predaje: 15. u mjesecu za prethodni mjesec
Predaja: DZS (Državni zavod za statistiku) putem web aplikacije

Referenca: Zakon o službenoj statistici, Uredba EU 2019/2152
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.intrastat")

# Pragovi za obvezno izvještavanje
PRAG_PRIMITAK = 400_000.0  # EUR godišnje
PRAG_OTPREMA = 300_000.0   # EUR godišnje

# Vrste kretanja
PRIMITAK = "primitak"   # Roba ulazi u RH iz EU
OTPREMA = "otprema"     # Roba izlazi iz RH u EU


@dataclass
class IntrastatStavka:
    """Jedna stavka Intrastat prijave."""
    tarifni_broj: str = ""          # 8-znamenkasti CN kod
    opis_robe: str = ""
    zemlja_partner: str = ""        # ISO 2-char (DE, IT, AT...)
    masa_kg: float = 0.0
    fakturna_vrijednost_eur: float = 0.0
    statisticka_vrijednost_eur: float = 0.0  # Uključuje troškove prijevoza
    vrsta_posla: str = "11"         # 11=kupoprodaja (najčešća)
    uvjeti_isporuke: str = "EXW"    # Incoterms
    vrsta_prijevoza: str = "3"      # 3=cestovni (najčešći za RH)
    zemlja_podrijetla: str = ""     # Samo za primitak
    regija: str = "HR04"            # NUTS2 regija

    # Interni tracking
    broj_racuna: str = ""
    datum_racuna: str = ""
    dobavljac_kupac: str = ""


@dataclass
class IntrastatPrijava:
    """Mjesečna Intrastat prijava."""
    godina: int = 0
    mjesec: int = 0
    vrsta: str = PRIMITAK  # primitak ili otprema
    oib: str = ""
    naziv: str = ""
    stavke: List[IntrastatStavka] = field(default_factory=list)
    ukupna_vrijednost: float = 0.0
    ukupna_masa: float = 0.0
    broj_stavki: int = 0
    warnings: List[str] = field(default_factory=list)


class IntrastatEngine:
    """Priprema Intrastat prijava."""

    def __init__(self):
        self._primitak_ytd: float = 0.0
        self._otprema_ytd: float = 0.0
        self._count = 0

    def check_obligation(
        self, primitak_ytd: float = 0.0, otprema_ytd: float = 0.0
    ) -> Dict[str, Any]:
        """Provjeri je li tvrtka obveznik Intrastat-a."""
        return {
            "primitak": {
                "ytd": primitak_ytd,
                "prag": PRAG_PRIMITAK,
                "obveznik": primitak_ytd >= PRAG_PRIMITAK,
                "preostalo_do_praga": max(0, PRAG_PRIMITAK - primitak_ytd),
            },
            "otprema": {
                "ytd": otprema_ytd,
                "prag": PRAG_OTPREMA,
                "obveznik": otprema_ytd >= PRAG_OTPREMA,
                "preostalo_do_praga": max(0, PRAG_OTPREMA - otprema_ytd),
            },
        }

    def create_prijava(
        self,
        godina: int,
        mjesec: int,
        vrsta: str,
        stavke: List[IntrastatStavka],
        oib: str = "",
        naziv: str = "",
    ) -> IntrastatPrijava:
        """Kreiraj mjesečnu Intrastat prijavu."""
        prijava = IntrastatPrijava(
            godina=godina, mjesec=mjesec, vrsta=vrsta,
            oib=oib, naziv=naziv,
        )

        for s in stavke:
            errs = self._validate_stavka(s, vrsta)
            if errs:
                prijava.warnings.extend(errs)

        prijava.stavke = stavke
        prijava.broj_stavki = len(stavke)
        prijava.ukupna_vrijednost = round(
            sum(s.fakturna_vrijednost_eur for s in stavke), 2
        )
        prijava.ukupna_masa = round(sum(s.masa_kg for s in stavke), 2)

        # Upozorenja
        if prijava.broj_stavki == 0:
            prijava.warnings.append("⚠️ Nema stavki u prijavi")

        rok = f"15.{mjesec + 1 if mjesec < 12 else 1:02d}.{godina if mjesec < 12 else godina + 1}"
        prijava.warnings.append(f"ℹ️ Rok predaje DZS-u: {rok}")

        self._count += 1
        return prijava

    def aggregate_by_country(self, prijava: IntrastatPrijava) -> List[Dict]:
        """Agregiraj stavke po zemlji partneru."""
        by_country: Dict[str, Dict] = {}
        for s in prijava.stavke:
            key = s.zemlja_partner
            if key not in by_country:
                by_country[key] = {
                    "zemlja": key,
                    "broj_stavki": 0,
                    "vrijednost": 0.0,
                    "masa_kg": 0.0,
                }
            by_country[key]["broj_stavki"] += 1
            by_country[key]["vrijednost"] += s.fakturna_vrijednost_eur
            by_country[key]["masa_kg"] += s.masa_kg

        result = sorted(by_country.values(), key=lambda x: x["vrijednost"], reverse=True)
        for r in result:
            r["vrijednost"] = round(r["vrijednost"], 2)
            r["masa_kg"] = round(r["masa_kg"], 2)
        return result

    def to_dict(self, prijava: IntrastatPrijava) -> Dict[str, Any]:
        return {
            "obrazac": "Intrastat",
            "vrsta": prijava.vrsta,
            "period": f"{prijava.mjesec:02d}/{prijava.godina}",
            "oib": prijava.oib,
            "naziv": prijava.naziv,
            "broj_stavki": prijava.broj_stavki,
            "ukupna_vrijednost": prijava.ukupna_vrijednost,
            "ukupna_masa_kg": prijava.ukupna_masa,
            "po_zemlji": self.aggregate_by_country(prijava),
            "predaja": "DZS web aplikacija",
            "warnings": prijava.warnings,
            "requires_approval": True,
        }

    def _validate_stavka(self, s: IntrastatStavka, vrsta: str) -> List[str]:
        errors = []
        if not s.tarifni_broj or len(s.tarifni_broj) < 8:
            errors.append(f"⚠️ Tarifni broj mora imati 8 znamenki: '{s.tarifni_broj}'")
        if not s.zemlja_partner or len(s.zemlja_partner) != 2:
            errors.append(f"⚠️ Zemlja partnera mora biti ISO 2-char: '{s.zemlja_partner}'")
        if s.zemlja_partner and s.zemlja_partner.upper() == "HR":
            errors.append("⛔ Zemlja partnera ne može biti HR (domaći promet)")
        if vrsta == PRIMITAK and not s.zemlja_podrijetla:
            errors.append("⚠️ Zemlja podrijetla obavezna za primitak")
        if s.fakturna_vrijednost_eur <= 0:
            errors.append("⚠️ Fakturna vrijednost mora biti > 0")
        return errors

    def get_stats(self):
        return {"intrastat_generated": self._count}
