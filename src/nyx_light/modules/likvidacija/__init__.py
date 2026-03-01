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

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.likvidacija")


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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Invoice matching, approval workflow, aging
# ════════════════════════════════════════════════════════

from datetime import date, timedelta
from enum import Enum


class InvoiceStatus(str, Enum):
    PRIMLJEN = "primljen"          # Račun zaprimljen
    U_OBRADI = "u_obradi"         # AI obradio, čeka provjeru
    ODOBREN = "odobren"           # Računovođa odobrio
    KNJIZEN = "knjizen"           # Proknjižen u ERP
    PLACEN = "placen"             # Plaćen
    OSPOREN = "osporen"           # Osporen — zahtijeva provjeru


class InvoiceMatchResult:
    """Rezultat sparivanja ulaznog računa s narudžbenicom."""
    def __init__(self):
        self.matched: bool = False
        self.order_ref: str = ""
        self.price_match: bool = False
        self.quantity_match: bool = False
        self.price_diff: float = 0.0
        self.notes: List[str] = []


class LikvidaturaEngine:
    """Likvidacija ulaznih računa — workflow od prijema do plaćanja."""

    def __init__(self):
        self._invoices = {}
        self._stats = {"total": 0, "approved": 0, "disputed": 0}

    def receive_invoice(self, invoice_data: dict) -> dict:
        """Zaprimi ulazni račun i pokreni likvidaturu."""
        inv_id = f"URA-{self._stats['total'] + 1:05d}"
        self._stats["total"] += 1

        # Automatska provjera
        checks = self._auto_checks(invoice_data)
        status = InvoiceStatus.U_OBRADI if all(
            c["passed"] for c in checks
        ) else InvoiceStatus.OSPOREN

        record = {
            "id": inv_id,
            "status": status.value,
            "partner": invoice_data.get("partner", ""),
            "oib": invoice_data.get("oib", ""),
            "broj_racuna": invoice_data.get("broj_racuna", ""),
            "datum_racuna": invoice_data.get("datum", ""),
            "datum_prijema": date.today().isoformat(),
            "iznos": _r2(_d(invoice_data.get("ukupno", 0))),
            "pdv": _r2(_d(invoice_data.get("pdv", 0))),
            "valuta": invoice_data.get("valuta", date.today().isoformat()),
            "checks": checks,
            "requires_approval": True,
        }
        self._invoices[inv_id] = record
        return record

    def _auto_checks(self, data: dict) -> List[dict]:
        """Automatske kontrole ulaznog računa."""
        checks = []

        # 1. OIB validan?
        oib = data.get("oib", "")
        oib_valid = len(oib) == 11 and oib.isdigit()
        checks.append({"check": "OIB format", "passed": oib_valid,
                       "msg": "OK" if oib_valid else f"Neispravan OIB: {oib}"})

        # 2. Datum u prošlosti?
        datum = data.get("datum", "")
        try:
            d = date.fromisoformat(datum)
            date_ok = d <= date.today()
            checks.append({"check": "Datum", "passed": date_ok,
                          "msg": "OK" if date_ok else "Datum u budućnosti"})
        except (ValueError, TypeError):
            checks.append({"check": "Datum", "passed": False, "msg": "Neispravan datum"})

        # 3. PDV = osnovica × stopa?
        ukupno = _d(data.get("ukupno", 0))
        pdv = _d(data.get("pdv", 0))
        osnovica = _d(data.get("osnovica", 0))
        if osnovica > 0 and pdv > 0:
            expected_total = _r2(osnovica + pdv)
            diff = abs(float(ukupno) - expected_total)
            math_ok = diff < 0.03
            checks.append({"check": "Matematika", "passed": math_ok,
                          "msg": "OK" if math_ok else f"Ukupno {ukupno} ≠ {osnovica}+{pdv}={expected_total}"})

        # 4. Duplikat?
        dup_key = f"{data.get('oib','')}_{data.get('broj_racuna','')}"
        is_dup = any(
            f"{inv['oib']}_{inv['broj_racuna']}" == dup_key
            for inv in self._invoices.values()
        )
        checks.append({"check": "Duplikat", "passed": not is_dup,
                       "msg": "Nema duplikata" if not is_dup else "⚠️ Moguć duplikat!"})

        return checks

    def approve(self, inv_id: str, approver: str) -> dict:
        """Odobri račun za knjiženje."""
        if inv_id not in self._invoices:
            return {"error": f"Račun {inv_id} ne postoji"}
        inv = self._invoices[inv_id]
        inv["status"] = InvoiceStatus.ODOBREN.value
        inv["approved_by"] = approver
        inv["approved_at"] = date.today().isoformat()
        self._stats["approved"] += 1
        return inv

    def get_aging_report(self) -> List[dict]:
        """Starosna struktura neplaćenih računa."""
        today = date.today()
        aging = {"0-30": [], "31-60": [], "61-90": [], "90+": []}
        for inv in self._invoices.values():
            if inv["status"] in (InvoiceStatus.PLACEN.value,):
                continue
            try:
                valuta = date.fromisoformat(inv["valuta"])
                days = (today - valuta).days
                if days <= 30:
                    aging["0-30"].append(inv)
                elif days <= 60:
                    aging["31-60"].append(inv)
                elif days <= 90:
                    aging["61-90"].append(inv)
                else:
                    aging["90+"].append(inv)
            except (ValueError, TypeError):
                pass

        return {
            bucket: {
                "count": len(items),
                "total": _r2(sum(_d(i["iznos"]) for i in items)),
            }
            for bucket, items in aging.items()
        }

    def get_stats(self):
        return {**self._stats, "pending": self._stats["total"] - self._stats["approved"] - self._stats["disputed"]}
