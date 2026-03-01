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

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.intrastat")


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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Pragovi obveze, CN8 šifre, DZS validacija
# ════════════════════════════════════════════════════════

from datetime import date

# Pragovi za Intrastat prijavu 2026. (DZS)
PRAG_OTPREMA = 400000     # EUR godišnje za otpremu
PRAG_PRIMITAK = 300000    # EUR godišnje za primitak

# Vrsta posla
VRSTA_POSLA = {
    "11": "Kupnja/prodaja",
    "12": "Povrat robe",
    "21": "Besplatna isporuka",
    "31": "Prelazak granice bez promjene vlasništva (dorada)",
    "41": "Isporuka nakon dorade",
    "51": "Popravak",
    "71": "Financijski leasing",
    "91": "Najam (operativni leasing)",
}

# Uvjeti isporuke (Incoterms 2020)
INCOTERMS = ["EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP",
             "FAS", "FOB", "CFR", "CIF"]

# Način prijevoza
NACIN_PRIJEVOZA = {
    "1": "Pomorski",
    "2": "Željeznički",
    "3": "Cestovni",
    "4": "Zračni",
    "5": "Poštanska pošiljka",
    "7": "Fiksne instalacije (cjevovod, dalekovod)",
    "8": "Unutarnji plovni putovi",
    "9": "Vlastiti pogon",
}


class IntrastatValidator:
    """Validacija Intrastat prijave za DZS."""

    @staticmethod
    def check_threshold(
        otpreme_godisnje: float = 0,
        primitci_godisnje: float = 0,
    ) -> dict:
        """Provjeri da li subjekt ima obvezu Intrastat prijave."""
        obveza_otprema = otpreme_godisnje >= PRAG_OTPREMA
        obveza_primitak = primitci_godisnje >= PRAG_PRIMITAK
        return {
            "obveza_otprema": obveza_otprema,
            "obveza_primitak": obveza_primitak,
            "otpreme_godisnje": _r2(_d(otpreme_godisnje)),
            "primitci_godisnje": _r2(_d(primitci_godisnje)),
            "prag_otprema": PRAG_OTPREMA,
            "prag_primitak": PRAG_PRIMITAK,
            "napomena": (
                "Intrastat prijava se podnosi DZS-u do 20. u mjesecu "
                "za prethodni mjesec. Obrazac IDO-1 (otprema) / IDP-1 (primitak)."
            ),
        }

    @staticmethod
    def validate_stavka(stavka: dict) -> List[dict]:
        """Validiraj jednu Intrastat stavku."""
        errors = []

        # CN8 šifra — 8 znamenki
        cn8 = stavka.get("cn8", "")
        if not cn8 or len(cn8) != 8 or not cn8.isdigit():
            errors.append({
                "field": "cn8", "msg": f"CN8 šifra mora imati 8 znamenki: '{cn8}'",
                "severity": "error",
            })

        # Zemlja partnera — ISO 2
        zemlja = stavka.get("zemlja_partnera", "")
        eu_zemlje = {"AT","BE","BG","CY","CZ","DE","DK","EE","ES","FI","FR",
                     "GR","HU","IE","IT","LT","LU","LV","MT","NL","PL","PT",
                     "RO","SE","SI","SK"}
        if zemlja and zemlja not in eu_zemlje:
            errors.append({
                "field": "zemlja_partnera",
                "msg": f"Zemlja '{zemlja}' nije EU članica ili nije ISO format",
                "severity": "error",
            })

        # Masa u kg
        masa = stavka.get("masa_kg", 0)
        if masa <= 0:
            errors.append({
                "field": "masa_kg", "msg": "Masa mora biti > 0 kg",
                "severity": "warning",
            })

        # Vrijednost
        vrijednost = stavka.get("fakturna_vrijednost", 0)
        if vrijednost <= 0:
            errors.append({
                "field": "fakturna_vrijednost", "msg": "Fakturna vrijednost mora biti > 0",
                "severity": "error",
            })

        # Vrsta posla
        vp = stavka.get("vrsta_posla", "")
        if vp and vp not in VRSTA_POSLA:
            errors.append({
                "field": "vrsta_posla",
                "msg": f"Nepoznata vrsta posla: '{vp}'. Dopuštene: {list(VRSTA_POSLA.keys())}",
                "severity": "error",
            })

        return errors

    @staticmethod
    def summary_monthly(stavke: list) -> dict:
        """Sumarni pregled za mjesečnu prijavu."""
        total_otprema = _d(0)
        total_primitak = _d(0)
        zemlje = set()
        for s in stavke:
            zemlje.add(s.get("zemlja_partnera", "??"))
            val = _d(s.get("fakturna_vrijednost", 0))
            if s.get("smjer") == "otprema":
                total_otprema += val
            else:
                total_primitak += val
        return {
            "otprema": _r2(total_otprema),
            "primitak": _r2(total_primitak),
            "ukupno": _r2(total_otprema + total_primitak),
            "broj_stavki": len(stavke),
            "zemlje": sorted(zemlje),
            "rok_predaje": f"20. u sljedećem mjesecu",
        }
