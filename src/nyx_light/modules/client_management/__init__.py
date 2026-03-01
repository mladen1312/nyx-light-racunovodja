"""
Modul E3 — Onboarding novog klijenta

Kad računovodstveni ured prima novog klijenta:
  1. Unos osnovnih podataka (OIB, naziv, tip poduzetnika)
  2. Automatska provjera OIB-a
  3. Konfiguracija ERP konektora (CPP/Synesis)
  4. Kreiranje kontnog plana (ili import postojećeg)
  5. Postavljanje poreznih parametara (PDV obveznik, stopa poreza na dobit)
  6. Kreiranje checklist-e za preuzimanje dokumentacije
  7. Inicijalna memorija (L2) za klijentova pravila
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.client_management")


@dataclass
class ClientProfile:
    """Kompletni profil klijenta."""
    client_id: str
    oib: str
    naziv: str
    tip: str = "d.o.o."  # d.o.o., j.d.o.o., d.d., obrt, pausalni_obrt
    adresa: str = ""
    email: str = ""
    kontakt_osoba: str = ""
    telefon: str = ""

    # Porezni parametri
    pdv_obveznik: bool = True
    pdv_period: str = "mjesecno"  # mjesecno, tromjesecno
    stopa_poreza_dobit: float = 18.0  # 10% ili 18%
    pausalni_porez: bool = False

    # ERP
    erp_type: str = "cpp"  # cpp, synesis, pantheon
    erp_config: Dict[str, Any] = field(default_factory=dict)

    # Datumi
    pocetak_suradnje: str = ""
    kraj_poslovne_godine: str = "12-31"  # MM-DD

    # Odgovorni
    racunovodja: str = ""  # user_id odgovornog računovođe

    # Status
    status: str = "aktivan"  # aktivan, neaktivan, u_prijenosu
    created_at: str = ""


@dataclass
class OnboardingChecklist:
    """Checklist dokumentacije za preuzimanje klijenta."""
    items: List[Dict[str, Any]] = field(default_factory=list)
    completed: int = 0
    total: int = 0


class ClientOnboarding:
    """Upravljanje procesom onboardinga novog klijenta."""

    # Standardna checklist dokumentacija
    STANDARD_DOCS = [
        {"doc": "Izvadak iz sudskog registra", "required": True,
         "tip": ["d.o.o.", "j.d.o.o.", "d.d."]},
        {"doc": "Obrtnica", "required": True,
         "tip": ["obrt", "pausalni_obrt"]},
        {"doc": "OIB potvrda", "required": True, "tip": "svi"},
        {"doc": "PDV prijava (zadnja)", "required": True,
         "tip": "pdv_obveznik"},
        {"doc": "Bruto bilanca tekuće godine", "required": True, "tip": "svi"},
        {"doc": "Kontni plan", "required": True, "tip": "svi"},
        {"doc": "Kartica svih otvorenih stavki", "required": True, "tip": "svi"},
        {"doc": "Popis osnovnih sredstava", "required": True, "tip": "svi"},
        {"doc": "Ugovori o radu zaposlenika", "required": True,
         "tip": "ima_zaposlenike"},
        {"doc": "Bankovna potvrda o računima", "required": True, "tip": "svi"},
        {"doc": "Zadnji GFI (bilanca + RDG)", "required": False, "tip": "svi"},
        {"doc": "Porezna prijava (PD/DOH)", "required": False, "tip": "svi"},
        {"doc": "Ugovor o najmu poslovnog prostora", "required": False,
         "tip": "svi"},
    ]

    def __init__(self):
        self._clients: Dict[str, ClientProfile] = {}
        self._checklists: Dict[str, OnboardingChecklist] = {}

    def start_onboarding(self, oib: str, naziv: str,
                         tip: str = "d.o.o.",
                         **kwargs) -> Dict[str, Any]:
        """Pokreni onboarding novog klijenta."""
        from nyx_light.modules.invoice_ocr.extractor import validate_oib

        # Validiraj OIB
        if not validate_oib(oib):
            return {"ok": False, "error": f"Neispravan OIB: {oib}"}

        # Generiraj client_id
        client_id = f"K{oib[-4:]}"

        # Kreiraj profil
        profile = ClientProfile(
            client_id=client_id,
            oib=oib,
            naziv=naziv,
            tip=tip,
            created_at=datetime.now().isoformat(),
            pocetak_suradnje=date.today().isoformat(),
            **{k: v for k, v in kwargs.items()
               if hasattr(ClientProfile, k)},
        )

        # Auto-config na temelju tipa
        if tip == "pausalni_obrt":
            profile.pdv_obveznik = False
            profile.pausalni_porez = True
            profile.stopa_poreza_dobit = 0
        elif tip in ("d.o.o.", "d.d."):
            profile.stopa_poreza_dobit = 10.0 if kwargs.get(
                "prihodi_ispod_1m", True) else 18.0

        self._clients[client_id] = profile

        # Generiraj checklist
        checklist = self._generate_checklist(profile)
        self._checklists[client_id] = checklist

        logger.info("Onboarding started: %s (%s) — %s",
                     naziv, oib, tip)

        return {
            "ok": True,
            "client_id": client_id,
            "profile": self._profile_to_dict(profile),
            "checklist": {
                "total": checklist.total,
                "items": checklist.items,
            },
        }

    def _generate_checklist(self, profile: ClientProfile) -> OnboardingChecklist:
        """Generiraj checklist prilagođenu tipu klijenta."""
        items = []
        for doc in self.STANDARD_DOCS:
            tip = doc["tip"]
            include = False
            if tip == "svi":
                include = True
            elif tip == "pdv_obveznik":
                include = profile.pdv_obveznik
            elif tip == "ima_zaposlenike":
                include = True  # Po defaultu pretpostavljamo
            elif isinstance(tip, list):
                include = profile.tip in tip
            elif profile.tip == tip:
                include = True

            if include:
                items.append({
                    "doc": doc["doc"],
                    "required": doc["required"],
                    "received": False,
                    "date_received": None,
                    "notes": "",
                })

        return OnboardingChecklist(items=items, total=len(items))

    def mark_doc_received(self, client_id: str, doc_name: str,
                          notes: str = "") -> Dict[str, Any]:
        """Označi dokument kao primljen."""
        cl = self._checklists.get(client_id)
        if not cl:
            return {"ok": False, "error": "Klijent nema checklist"}

        for item in cl.items:
            if item["doc"].lower() == doc_name.lower():
                item["received"] = True
                item["date_received"] = date.today().isoformat()
                item["notes"] = notes
                cl.completed = sum(1 for i in cl.items if i["received"])
                return {"ok": True, "completed": cl.completed,
                        "total": cl.total,
                        "progress": f"{cl.completed}/{cl.total}"}

        return {"ok": False, "error": f"Dokument '{doc_name}' nije na listi"}

    def get_checklist_status(self, client_id: str) -> Dict[str, Any]:
        cl = self._checklists.get(client_id)
        if not cl:
            return {"ok": False, "error": "Nema checklist"}
        missing = [i["doc"] for i in cl.items
                   if not i["received"] and i["required"]]
        return {
            "completed": cl.completed,
            "total": cl.total,
            "progress_pct": round(cl.completed / cl.total * 100)
            if cl.total else 0,
            "missing_required": missing,
            "ready": len(missing) == 0,
        }

    def get_client(self, client_id: str) -> Optional[Dict]:
        p = self._clients.get(client_id)
        return self._profile_to_dict(p) if p else None

    def list_clients(self) -> List[Dict]:
        return [self._profile_to_dict(p) for p in self._clients.values()]

    def _profile_to_dict(self, p: ClientProfile) -> Dict:
        return {
            "client_id": p.client_id,
            "oib": p.oib,
            "naziv": p.naziv,
            "tip": p.tip,
            "pdv_obveznik": p.pdv_obveznik,
            "stopa_poreza_dobit": p.stopa_poreza_dobit,
            "erp_type": p.erp_type,
            "racunovodja": p.racunovodja,
            "status": p.status,
            "pocetak_suradnje": p.pocetak_suradnje,
        }

    def get_stats(self):
        return {"total_clients": len(self._clients),
                "active": sum(1 for c in self._clients.values()
                              if c.status == "aktivan")}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Profitabilnost klijenta, rizik scoring, portfolio analiza
# ════════════════════════════════════════════════════════

from decimal import Decimal, ROUND_HALF_UP
from datetime import date

def _d(val) -> Decimal:
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val) -> float:
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Kategorije klijenata prema veličini (ZOR)
VELICINA_PODUZETNIKA = {
    "mikro": {"aktiva_max": 350000, "prihod_max": 700000, "zaposleni_max": 10},
    "mali": {"aktiva_max": 2000000, "prihod_max": 8000000, "zaposleni_max": 50},
    "srednji": {"aktiva_max": 17500000, "prihod_max": 35000000, "zaposleni_max": 250},
    "veliki": {"aktiva_max": float('inf'), "prihod_max": float('inf'), "zaposleni_max": float('inf')},
}


class ClientProfitability:
    """Analiza profitabilnosti klijenata ureda."""

    @staticmethod
    def calculate(
        klijent_id: str,
        mjesecna_naknada: float,
        procijenjeni_sati_mj: float,
        satnica_zaposlenik: float = 20.0,  # EUR/h prosječna cijena rada
        dodatni_troskovi_mj: float = 0,
    ) -> dict:
        """Izračun profitabilnosti po klijentu."""
        prihod = _d(mjesecna_naknada)
        trosak_rada = _r2(_d(procijenjeni_sati_mj) * _d(satnica_zaposlenik))
        ukupni_trosak = _r2(_d(trosak_rada) + _d(dodatni_troskovi_mj))
        dobit = _r2(prihod - _d(ukupni_trosak))
        marza = _r2(_d(dobit) / prihod * 100) if prihod > 0 else 0

        return {
            "klijent_id": klijent_id,
            "mjesecna_naknada": _r2(prihod),
            "trosak_rada": trosak_rada,
            "dodatni_troskovi": _r2(_d(dodatni_troskovi_mj)),
            "ukupni_trosak": ukupni_trosak,
            "dobit_mjesecna": dobit,
            "marza_pct": marza,
            "godisnja_dobit": _r2(_d(dobit) * 12),
            "efektivna_satnica": _r2(prihod / _d(procijenjeni_sati_mj or 1)),
            "ocjena": (
                "✅ profitabilan" if marza > 20
                else "⚠️ granično" if marza > 5
                else "❌ neprofitabilan"
            ),
        }

    @staticmethod
    def classify_client(
        aktiva: float, prihod: float, zaposleni: int
    ) -> dict:
        """Klasifikacija klijenta prema ZOR-u (mikro/mali/srednji/veliki)."""
        for cat, limits in VELICINA_PODUZETNIKA.items():
            criteria_met = 0
            if aktiva <= limits["aktiva_max"]:
                criteria_met += 1
            if prihod <= limits["prihod_max"]:
                criteria_met += 1
            if zaposleni <= limits["zaposleni_max"]:
                criteria_met += 1
            # Dva od tri kriterija (ZOR čl. 5)
            if criteria_met >= 2:
                return {
                    "kategorija": cat,
                    "aktiva": _r2(_d(aktiva)),
                    "prihod": _r2(_d(prihod)),
                    "zaposleni": zaposleni,
                    "obveze": {
                        "mikro": "Jednostavno knjigovodstvo moguće, bez revizije",
                        "mali": "Dvojno knjigovodstvo, bez revizije (osim iznimki)",
                        "srednji": "Dvojno knjigovodstvo, revizija obvezna",
                        "veliki": "Dvojno knjigovodstvo, revizija, konsolidacija",
                    }.get(cat, ""),
                    "gfi_rok": "30. travnja" if cat in ("mikro", "mali") else "30. lipnja",
                    "zakonski_temelj": "Zakon o računovodstvu, čl. 5",
                }
        return {"kategorija": "veliki"}

    @staticmethod
    def portfolio_summary(klijenti: list) -> dict:
        """Sumarni pregled portfolia klijenata."""
        ukupno_prihod = _d(0)
        ukupno_dobit = _d(0)
        by_cat = {}
        for k in klijenti:
            cat = k.get("kategorija", "nepoznato")
            by_cat[cat] = by_cat.get(cat, 0) + 1
            ukupno_prihod += _d(k.get("mjesecna_naknada", 0))
            ukupno_dobit += _d(k.get("dobit_mjesecna", 0))

        return {
            "broj_klijenata": len(klijenti),
            "po_kategorijama": by_cat,
            "ukupni_mjesecni_prihod": _r2(ukupno_prihod),
            "ukupna_mjesecna_dobit": _r2(ukupno_dobit),
            "prosjecna_marza": _r2(
                ukupno_dobit / ukupno_prihod * 100
            ) if ukupno_prihod > 0 else 0,
        }


# ════════════════════════════════════════════════════════
# PROŠIRENJA: PDV obveznik provjera, OIB validacija, RGFI check
# ════════════════════════════════════════════════════════

from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def _d(val):
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val):
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Pragovi za PDV obveznika i veličinu poduzetnika (ZOR čl. 5)
PRAG_PDV_OBVEZNIK = 40000.0       # EUR godišnje (od 2025.)
PRAG_MIKRO_PRIHODI = 2600000.0    # EUR
PRAG_MIKRO_IMOVINA = 1300000.0    # EUR
PRAG_MIKRO_ZAPOSLENICI = 10
PRAG_MALI_PRIHODI = 7500000.0
PRAG_MALI_IMOVINA = 3750000.0
PRAG_MALI_ZAPOSLENICI = 50
PRAG_SREDNJI_PRIHODI = 30000000.0
PRAG_SREDNJI_IMOVINA = 15000000.0
PRAG_SREDNJI_ZAPOSLENICI = 250


def validate_oib(oib: str) -> bool:
    """Validacija OIB-a po ISO 7064, MOD 11,10."""
    if not oib or len(oib) != 11 or not oib.isdigit():
        return False
    a = 10
    for digit in oib[:10]:
        a = (a + int(digit)) % 10
        if a == 0:
            a = 10
        a = (a * 2) % 11
    return (11 - a) % 10 == int(oib[10])


class ClientClassifier:
    """Klasifikacija klijenata prema zakonskim kriterijima."""

    @staticmethod
    def classify_size(
        prihodi: float,
        imovina: float,
        zaposlenici: int,
    ) -> dict:
        """Klasificiraj poduzetnika po veličini (ZOR čl. 5)."""
        if (prihodi <= PRAG_MIKRO_PRIHODI and
            imovina <= PRAG_MIKRO_IMOVINA and
            zaposlenici <= PRAG_MIKRO_ZAPOSLENICI):
            cat = "mikro"
            gfi = "GFI-POD (skraćeni)"
            revizija = False
        elif (prihodi <= PRAG_MALI_PRIHODI and
              imovina <= PRAG_MALI_IMOVINA and
              zaposlenici <= PRAG_MALI_ZAPOSLENICI):
            cat = "mali"
            gfi = "GFI-POD (skraćeni)"
            revizija = False
        elif (prihodi <= PRAG_SREDNJI_PRIHODI and
              imovina <= PRAG_SREDNJI_IMOVINA and
              zaposlenici <= PRAG_SREDNJI_ZAPOSLENICI):
            cat = "srednji"
            gfi = "GFI-POD (potpuni)"
            revizija = True
        else:
            cat = "veliki"
            gfi = "GFI-POD (potpuni) + konsolidacija"
            revizija = True

        return {
            "kategorija": cat,
            "gfi_obrazac": gfi,
            "revizija_obvezna": revizija,
            "standardi": "HSFI" if cat in ("mikro", "mali") else "MSFI",
            "pdv_obveznik": prihodi > PRAG_PDV_OBVEZNIK,
            "intrastat_moguc": prihodi > 300000,
            "zakonski_temelj": "Zakon o računovodstvu čl. 5",
        }

    @staticmethod
    def validate_client(data: dict) -> list:
        """Validacija klijentskih podataka."""
        errors = []
        oib = data.get("oib", "")
        if oib and not validate_oib(oib):
            errors.append({"field": "oib", "msg": f"Neispravan OIB: {oib}", "severity": "error"})
        if not data.get("naziv"):
            errors.append({"field": "naziv", "msg": "Naziv klijenta je obvezan", "severity": "error"})
        if not data.get("adresa"):
            errors.append({"field": "adresa", "msg": "Adresa je obvezna za GFI", "severity": "warning"})
        iban = data.get("iban", "")
        if iban and (not iban.startswith("HR") or len(iban) != 21):
            errors.append({"field": "iban", "msg": f"IBAN format: HR + 19 znamenki, dobiveno: {iban}", "severity": "warning"})
        return errors

    @staticmethod
    def pdv_status_check(godisnji_prihod: float) -> dict:
        """Provjeri PDV obvezništvo."""
        is_obveznik = godisnji_prihod > PRAG_PDV_OBVEZNIK
        return {
            "pdv_obveznik": is_obveznik,
            "godisnji_prihod": _r2(_d(godisnji_prihod)),
            "prag": PRAG_PDV_OBVEZNIK,
            "pdv_prijava": "mjesečna" if godisnji_prihod > 800000 else "tromjesečna" if is_obveznik else "nije obveznik",
            "napomena": (
                "Poduzetnik s prihodom > 800.000 EUR predaje PDV mjesečno, "
                "ostali PDV obveznici tromjesečno."
            ) if is_obveznik else "Ispod praga — nije u sustavu PDV-a.",
        }
