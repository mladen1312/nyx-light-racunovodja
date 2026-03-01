"""
Nyx Light — Modul A8: Obračunske stavke

Checklist i podsjetnik za period-end stavke:
- Amortizacija
- Razgraničeni prihodi/rashodi
- Rezerviranja
- Zatezne kamate
- Korekcije prethodnog perioda

Ključna vrijednost: NIKAD ne izostaviti obračunsku stavku.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.accruals")


@dataclass
class AccrualItem:
    """Pojedina obračunska stavka."""
    name: str
    category: str              # amortizacija, razgraničenje, rezerviranje, kamata, korekcija
    frequency: str             # monthly, quarterly, yearly
    konto_duguje: str = ""
    konto_potrazuje: str = ""
    amount: Optional[float] = None  # None = zahtijeva izračun
    auto_calculable: bool = False
    notes: str = ""
    completed: bool = False


class AccrualsChecklist:
    """
    Period-end checklist za obračunske stavke.
    
    Osigurava da nijedna obračunska stavka ne bude izostavljena.
    AI predlaže iznos gdje je moguće (amortizacija), ostalo zahtijeva prosudbu.
    """

    # Standardni checklist za mjesečno/godišnje zaključivanje
    MONTHLY_ITEMS = [
        AccrualItem(
            name="Amortizacija dugotrajne materijalne imovine",
            category="amortizacija",
            frequency="monthly",
            konto_duguje="4300",
            konto_potrazuje="0290",
            auto_calculable=True,
            notes="Izračun na temelju evidencije OS i stopa iz Pravilnika",
        ),
        AccrualItem(
            name="Amortizacija nematerijalne imovine",
            category="amortizacija",
            frequency="monthly",
            konto_duguje="4300",
            konto_potrazuje="0190",
            auto_calculable=True,
        ),
        AccrualItem(
            name="Razgraničenje troškova najma (ako se plaća unaprijed)",
            category="razgraničenje",
            frequency="monthly",
            konto_duguje="4140",
            konto_potrazuje="1900",
            notes="Provjeriti ugovore o najmu — mjesečni udio",
        ),
        AccrualItem(
            name="Razgraničenje troškova osiguranja",
            category="razgraničenje",
            frequency="monthly",
            konto_duguje="4140",
            konto_potrazuje="1900",
            notes="Godišnja polica / 12 = mjesečni trošak",
        ),
        AccrualItem(
            name="Razgraničenje prihoda budućih razdoblja",
            category="razgraničenje",
            frequency="monthly",
            notes="Primljeni prihodi koji se odnose na buduća razdoblja",
        ),
    ]

    QUARTERLY_ITEMS = [
        AccrualItem(
            name="Provjera PDV-a — usklađivanje pretporeza",
            category="korekcija",
            frequency="quarterly",
            notes="Provjera prava na odbitak pretporeza za mješovite troškove",
        ),
    ]

    YEARLY_ITEMS = [
        AccrualItem(
            name="Godišnji obračun amortizacije (konačni)",
            category="amortizacija",
            frequency="yearly",
            auto_calculable=True,
            notes="Konačni godišnji obračun — usklađenje s mjesečnim akontacijama",
        ),
        AccrualItem(
            name="Usklađivanje zaliha s inventurnom listom",
            category="korekcija",
            frequency="yearly",
            notes="Manjkovi i viškovi — porezna priznatost ovisno o vrsti",
        ),
        AccrualItem(
            name="Ispravak vrijednosti potraživanja",
            category="rezerviranje",
            frequency="yearly",
            konto_duguje="4420",
            konto_potrazuje="1209",
            notes="Potraživanja starija od 60 dana (čl. 9. Zakona o porezu na dobit)",
        ),
        AccrualItem(
            name="Rezerviranja za sudske sporove",
            category="rezerviranje",
            frequency="yearly",
            notes="Prosudba računovođe — vjerojatnost i visina obveze (HSFI 13)",
        ),
        AccrualItem(
            name="Rezerviranja za otpremnine",
            category="rezerviranje",
            frequency="yearly",
            notes="Ako postoje radnici s pravom na otpremninu",
        ),
        AccrualItem(
            name="Obračun zateznih kamata",
            category="kamata",
            frequency="yearly",
            notes="Zatezne kamate na nepravodobno plaćene obveze",
        ),
        AccrualItem(
            name="Revalorizacija deviznih obveza/potraživanja",
            category="korekcija",
            frequency="yearly",
            notes="Tečajne razlike na 31.12. prema tečaju HNB",
        ),
        AccrualItem(
            name="Razgraničenja — provjera isteka",
            category="razgraničenje",
            frequency="yearly",
            notes="Provjeriti sva razgraničenja — ukinuti istekla",
        ),
        AccrualItem(
            name="Provjera dosljednosti računovodstvenih politika",
            category="korekcija",
            frequency="yearly",
            notes="Svaka promjena zahtijeva bilješku u GFI (HSFI 3)",
        ),
        AccrualItem(
            name="Porezno nepriznati rashodi — provjera",
            category="korekcija",
            frequency="yearly",
            notes="Reprezentacija (50%), kazne, darovi > limit, privatna upotreba vozila",
        ),
    ]

    def __init__(self):
        self._check_count = 0

    def get_checklist(
        self,
        period: str = "monthly",
        client_id: str = "",
        custom_items: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generiraj checklist za zaključivanje perioda.
        
        period: "monthly", "quarterly", "yearly"
        """
        items = list(self.MONTHLY_ITEMS)  # Uvijek uključi mjesečne

        if period in ("quarterly", "yearly"):
            items.extend(self.QUARTERLY_ITEMS)

        if period == "yearly":
            items.extend(self.YEARLY_ITEMS)

        # Dodaj custom stavke za klijenta
        if custom_items:
            for ci in custom_items:
                items.append(AccrualItem(
                    name=ci.get("name", "Custom stavka"),
                    category=ci.get("category", "korekcija"),
                    frequency=period,
                    notes=ci.get("notes", ""),
                ))

        self._check_count += 1

        return {
            "period": period,
            "client_id": client_id,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_items": len(items),
            "auto_calculable": sum(1 for i in items if i.auto_calculable),
            "requires_judgment": sum(1 for i in items if not i.auto_calculable),
            "items": [
                {
                    "name": item.name,
                    "category": item.category,
                    "konto_duguje": item.konto_duguje,
                    "konto_potrazuje": item.konto_potrazuje,
                    "auto_calculable": item.auto_calculable,
                    "notes": item.notes,
                    "completed": item.completed,
                }
                for item in items
            ],
            "warning": "⚠️ Svi iznosi zahtijevaju odobrenje računovođe prije knjiženja",
        }

    def get_stats(self) -> Dict[str, Any]:
        return {"checklists_generated": self._check_count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: PVR/AVR kalkulacija, odgođeni prihodi/rashodi, godišnji obračun
# ════════════════════════════════════════════════════════

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

def _d(val) -> Decimal:
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val) -> float:
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Konta za razgraničenja (RPC 2023)
KONTA_AVR = {
    "unaprijed_placeni_troskovi": "0890",  # AVR - plaćeni troškovi budućeg r.
    "nezaracunani_prihodi": "1890",        # AVR - obračunati, nefakturirani
    "unaprijed_naplaceni_prihodi": "2940", # PVR - naplaćeni unaprijed
    "obracunani_troskovi": "2890",         # PVR - nastali, neplaćeni
    "rezerviranja_godisnji": "2920",       # Rezerviranja za godišnje odmore
    "rezerviranja_otpremnine": "2930",     # Rezerviranja za otpremnine
    "rezerviranja_sudski": "2940",         # Rezerviranja za sudske sporove
}


class AccrualEngine:
    """Upravljanje vremenskim razgraničenjima prema HSFI 14."""

    def __init__(self):
        self._count = 0

    def calculate_prepaid_expense(
        self,
        ukupni_iznos: float,
        datum_placanja: str,
        datum_pocetka: str,
        datum_zavrsetka: str,
        opis: str = "",
    ) -> dict:
        """AVR — unaprijed plaćeni trošak (npr. godišnje osiguranje, najam)."""
        try:
            pocetak = date.fromisoformat(datum_pocetka)
            zavrsetak = date.fromisoformat(datum_zavrsetka)
        except ValueError:
            return {"error": "Neispravan format datuma"}

        ukupno_dana = (zavrsetak - pocetak).days
        if ukupno_dana <= 0:
            return {"error": "Datum završetka mora biti nakon datuma početka"}

        dnevni_iznos = _r2(_d(ukupni_iznos) / _d(ukupno_dana))

        # Raspored po mjesecima
        raspored = []
        current = pocetak
        while current <= zavrsetak:
            mj_pocetak = current
            if current.month == 12:
                mj_zavrsetak = min(zavrsetak, date(current.year + 1, 1, 1) - timedelta(days=1))
            else:
                mj_zavrsetak = min(zavrsetak, date(current.year, current.month + 1, 1) - timedelta(days=1))

            dani_u_mj = (mj_zavrsetak - mj_pocetak).days + 1
            iznos_mj = _r2(_d(dnevni_iznos) * _d(dani_u_mj))

            raspored.append({
                "mjesec": mj_pocetak.strftime("%Y-%m"),
                "dani": dani_u_mj,
                "iznos": iznos_mj,
                "knjizenje": f"D {KONTA_AVR['unaprijed_placeni_troskovi']} / P trošak {iznos_mj}",
            })

            if mj_zavrsetak.month == 12:
                current = date(mj_zavrsetak.year + 1, 1, 1)
            else:
                current = date(mj_zavrsetak.year, mj_zavrsetak.month + 1, 1)

        self._count += 1
        return {
            "tip": "avr_unaprijed_placeni",
            "opis": opis,
            "ukupni_iznos": _r2(_d(ukupni_iznos)),
            "razdoblje": f"{datum_pocetka} — {datum_zavrsetka}",
            "ukupno_dana": ukupno_dana,
            "dnevni_iznos": dnevni_iznos,
            "raspored": raspored,
            "konto": KONTA_AVR["unaprijed_placeni_troskovi"],
            "zakonski_temelj": "HSFI 14 — Vremenska razgraničenja",
        }

    def rezerviranje_godisnji(
        self,
        broj_zaposlenika: int,
        prosjecna_placa: float,
        prosjecno_neiskoristenih_dana: float = 5.0,
    ) -> dict:
        """PVR — rezerviranje za neiskorištene godišnje odmore."""
        dnevni_trosak = _r2(_d(prosjecna_placa) / _d(22))  # 22 radna dana
        dnevni_s_doprinosima = _r2(_d(dnevni_trosak) * _d("1.165"))  # +16.5% ZO

        ukupno = _r2(
            _d(dnevni_s_doprinosima) * _d(prosjecno_neiskoristenih_dana) * _d(broj_zaposlenika)
        )

        self._count += 1
        return {
            "tip": "pvr_rezerviranje_godisnji",
            "broj_zaposlenika": broj_zaposlenika,
            "prosjecna_placa": _r2(_d(prosjecna_placa)),
            "dnevni_trosak_s_doprinosima": dnevni_s_doprinosima,
            "prosjecno_neiskoristenih_dana": prosjecno_neiskoristenih_dana,
            "ukupno_rezerviranje": ukupno,
            "konto": KONTA_AVR["rezerviranja_godisnji"],
            "knjizenje": f"D troškovi / P {KONTA_AVR['rezerviranja_godisnji']} — {ukupno} EUR",
        }

    def get_stats(self):
        return {"accruals_calculated": self._count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Razgraničenja (PVR/AVR), periodizacija, auto-storno
# ════════════════════════════════════════════════════════

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


def _d(val):
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val):
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Tipični primjeri razgraničenja u RH
ACCRUAL_TYPES = {
    # Pasivna vremenska razgraničenja (PVR) — konto 29xx
    "pvr_komunalije": {"konto": "2900", "opis": "Unaprijed naplaćeni prihodi (komunalije)"},
    "pvr_zakup": {"konto": "2910", "opis": "Unaprijed naplaćen zakup"},
    "pvr_13_placa": {"konto": "2920", "opis": "Rezerviranje za 13. plaću"},
    "pvr_godisnji_odmor": {"konto": "2921", "opis": "Rezerviranje za neiskorišteni GO"},
    "pvr_otpremnina": {"konto": "2922", "opis": "Rezerviranje za otpremnine"},
    "pvr_bonus": {"konto": "2930", "opis": "Rezerviranje za bonuse"},
    # Aktivna vremenska razgraničenja (AVR) — konto 19xx
    "avr_osiguranje": {"konto": "1900", "opis": "Unaprijed plaćeno osiguranje"},
    "avr_zakup": {"konto": "1910", "opis": "Unaprijed plaćen zakup"},
    "avr_pretplata": {"konto": "1920", "opis": "Pretplate (software, časopisi)"},
    "avr_bonitet": {"konto": "1930", "opis": "Unaprijed plaćeni bonitet"},
}


class AccrualEngine:
    """Motor za razgraničenja — periodizacija troškova i prihoda."""

    def __init__(self):
        self._accruals = []
        self._count = 0

    def create_accrual(
        self,
        tip: str,
        ukupni_iznos: float,
        datum_pocetka: str,
        datum_zavrsetka: str,
        opis: str = "",
        klijent_id: str = "",
    ) -> dict:
        """Kreiraj razgraničenje s periodizacijom."""
        try:
            start = date.fromisoformat(datum_pocetka)
            end = date.fromisoformat(datum_zavrsetka)
        except ValueError:
            return {"error": "Neispravan format datuma (YYYY-MM-DD)"}

        if end <= start:
            return {"error": "Datum završetka mora biti nakon datuma početka"}

        # Broj mjeseci
        mjeseci = max(1, (end.year - start.year) * 12 + (end.month - start.month))
        mjesecni_iznos = _r2(_d(ukupni_iznos) / _d(mjeseci))

        # Generiraj raspored knjiženja
        raspored = []
        current = start
        for i in range(mjeseci):
            m = (current.month + i - 1) % 12 + 1
            y = current.year + (current.month + i - 1) // 12
            raspored.append({
                "mjesec": f"{y}-{m:02d}",
                "iznos": mjesecni_iznos,
                "storno": False,
            })

        accrual_info = ACCRUAL_TYPES.get(tip, {"konto": "2999", "opis": tip})
        accrual_id = f"ACR-{self._count + 1:04d}"
        self._count += 1

        record = {
            "id": accrual_id,
            "tip": tip,
            "konto": accrual_info["konto"],
            "opis": opis or accrual_info["opis"],
            "ukupni_iznos": _r2(_d(ukupni_iznos)),
            "mjesecni_iznos": mjesecni_iznos,
            "datum_pocetka": datum_pocetka,
            "datum_zavrsetka": datum_zavrsetka,
            "mjeseci": mjeseci,
            "raspored": raspored,
            "klijent_id": klijent_id,
            "status": "aktivan",
            "requires_approval": True,
        }
        self._accruals.append(record)
        return record

    def get_monthly_entries(self, year: int, month: int) -> list:
        """Dohvati sva knjiženja razgraničenja za mjesec."""
        period = f"{year}-{month:02d}"
        entries = []
        for acr in self._accruals:
            if acr["status"] != "aktivan":
                continue
            for r in acr["raspored"]:
                if r["mjesec"] == period and not r.get("booked"):
                    entries.append({
                        "accrual_id": acr["id"],
                        "tip": acr["tip"],
                        "konto": acr["konto"],
                        "iznos": r["iznos"],
                        "opis": f"{acr['opis']} — {period}",
                    })
        return entries

    def auto_storno(self, accrual_id: str) -> dict:
        """Storniraj razgraničenje — generira protustavke."""
        for acr in self._accruals:
            if acr["id"] == accrual_id:
                storno_entries = []
                for r in acr["raspored"]:
                    if not r.get("booked"):
                        storno_entries.append({
                            "mjesec": r["mjesec"],
                            "iznos": -r["iznos"],
                            "storno": True,
                        })
                acr["status"] = "storniran"
                return {"storno_entries": storno_entries, "accrual_id": accrual_id}
        return {"error": f"Razgraničenje {accrual_id} ne postoji"}

    def pvr_godisnji_odmor(self, zaposlenici: list) -> dict:
        """Izračun PVR za neiskorišteni godišnji odmor (čl. 19 HSFI 16)."""
        ukupno = _d(0)
        detalji = []
        for z in zaposlenici:
            dnevnica = _r2(_d(z.get("mjesecna_placa", 0)) / _d(z.get("radni_dani_mjesecno", 22)))
            neiskoristeno = z.get("neiskoristeni_dani", 0)
            iznos = _r2(_d(dnevnica) * _d(neiskoristeno) * _d("1.175"))  # bruto + 17.5% doprinosi
            ukupno += _d(iznos)
            detalji.append({
                "ime": z.get("ime", "?"),
                "dnevnica": dnevnica,
                "neiskoristeni_dani": neiskoristeno,
                "pvr_iznos": iznos,
            })
        return {
            "konto": "2921",
            "ukupno_pvr": _r2(ukupno),
            "broj_zaposlenika": len(zaposlenici),
            "detalji": detalji,
            "zakonski_temelj": "HSFI 16 — Rezerviranja, čl. 19",
        }

    def get_stats(self):
        active = sum(1 for a in self._accruals if a["status"] == "aktivan")
        return {"total": self._count, "active": active}
