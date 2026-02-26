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
