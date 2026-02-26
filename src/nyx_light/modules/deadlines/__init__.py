"""
Nyx Light — Modul F: Praćenje zakonskih rokova

Kalendar svih zakonskih rokova za porezne prijave i izvještaje.
Proaktivna obavijest zaposlenicima o predstojećim rokovima.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.deadlines")


@dataclass
class Deadline:
    name: str
    day_of_month: int        # Dan u mjesecu
    frequency: str           # monthly, quarterly, yearly
    months: List[int] = None # Za quarterly/yearly — koji mjeseci
    description: str = ""
    form: str = ""           # Naziv obrasca
    platform: str = ""       # ePorezna, eFINA, HZMO...
    penalty_info: str = ""


# ════════════════════════════════════════════════════════
# Fiksni zakonski rokovi u RH (2026.)
# ════════════════════════════════════════════════════════

ZAKONSKI_ROKOVI = [
    Deadline("PDV prijava (mjesečna)", 20, "monthly",
             form="PPO obrazac", platform="ePorezna",
             description="Predaja do 20. u mjesecu za prethodni mjesec"),
    Deadline("PDV prijava (tromjesečna)", 20, "quarterly", months=[1,4,7,10],
             form="PPO obrazac", platform="ePorezna",
             description="Predaja do 20. u mjesecu nakon završetka tromjesečja"),
    Deadline("JOPPD obrazac", 15, "monthly",
             form="JOPPD", platform="ePorezna",
             description="Predaja na dan isplate ili do 15. za prethodni mjesec"),
    Deadline("Intrastat prijava", 20, "monthly",
             platform="DZS",
             description="Mjesečna prijava robne razmjene s EU"),
    Deadline("EC Sales List (zbirna prijava)", 20, "monthly",
             platform="ePorezna",
             description="Zbirna prijava za usluge unutar EU"),
    Deadline("Porez na dobit (PD obrazac)", 30, "yearly", months=[4],
             form="PD obrazac", platform="ePorezna",
             description="Godišnja prijava do 30. travnja"),
    Deadline("Porez na dohodak (DOH)", 28, "yearly", months=[2],
             form="DOH obrazac", platform="ePorezna",
             description="Godišnja prijava do kraja veljače"),
    Deadline("GFI predaja FINA — standardni", 30, "yearly", months=[4],
             form="GFI-POD", platform="eFINA",
             description="Godišnji financijski izvještaj do 30. travnja"),
    Deadline("GFI predaja FINA — revizija", 30, "yearly", months=[6],
             form="GFI-POD", platform="eFINA",
             description="GFI za revizijski obvezne do 30. lipnja"),
    Deadline("Turistička zajednica (TZ)", 15, "quarterly", months=[1,4,7,10],
             form="TZ obrazac", platform="ePorezna",
             description="Tromjesečno"),
    Deadline("Paušalni obrt (KPR)", 15, "quarterly", months=[1,4,7,10],
             form="KPR obrazac", platform="ePorezna",
             description="Tromjesečni obračun paušalnog poreza"),
    Deadline("Statistički izvještaji (DZS)", 20, "quarterly", months=[1,4,7,10],
             platform="DZS/eFINA"),
    Deadline("Inventura — popis imovine", 31, "yearly", months=[12],
             description="Zakonska obveza popisa na 31.12."),
]


class DeadlineTracker:
    """Praćenje rokova po klijentima."""

    def __init__(self):
        self.deadlines = ZAKONSKI_ROKOVI

    def get_upcoming(self, days_ahead: int = 14, today: date = None) -> List[Dict]:
        """Dohvati rokove u sljedećih N dana."""
        today = today or date.today()
        end = today + timedelta(days=days_ahead)
        upcoming = []

        for dl in self.deadlines:
            next_date = self._next_occurrence(dl, today)
            if next_date and today <= next_date <= end:
                days_left = (next_date - today).days
                upcoming.append({
                    "name": dl.name,
                    "date": next_date.isoformat(),
                    "days_left": days_left,
                    "form": dl.form,
                    "platform": dl.platform,
                    "description": dl.description,
                    "urgency": "critical" if days_left <= 3 else
                               "warning" if days_left <= 7 else "normal",
                })

        return sorted(upcoming, key=lambda x: x["days_left"])

    def get_monthly_calendar(self, year: int, month: int) -> List[Dict]:
        """Generiraj kalendar rokova za mjesec."""
        check_date = date(year, month, 1)
        result = []

        for dl in self.deadlines:
            if dl.frequency == "monthly":
                day = min(dl.day_of_month, self._last_day(year, month))
                result.append({
                    "name": dl.name, "date": date(year, month, day).isoformat(),
                    "form": dl.form, "platform": dl.platform,
                })
            elif dl.frequency == "quarterly" and dl.months and month in dl.months:
                day = min(dl.day_of_month, self._last_day(year, month))
                result.append({
                    "name": dl.name, "date": date(year, month, day).isoformat(),
                    "form": dl.form, "platform": dl.platform,
                })
            elif dl.frequency == "yearly" and dl.months and month in dl.months:
                day = min(dl.day_of_month, self._last_day(year, month))
                result.append({
                    "name": dl.name, "date": date(year, month, day).isoformat(),
                    "form": dl.form, "platform": dl.platform,
                })

        return sorted(result, key=lambda x: x["date"])

    def _next_occurrence(self, dl: Deadline, today: date) -> date:
        """Izračunaj sljedeći datum roka."""
        year, month = today.year, today.month

        if dl.frequency == "monthly":
            day = min(dl.day_of_month, self._last_day(year, month))
            d = date(year, month, day)
            if d < today:
                month += 1
                if month > 12: year += 1; month = 1
                day = min(dl.day_of_month, self._last_day(year, month))
                d = date(year, month, day)
            return d

        if dl.frequency in ("quarterly", "yearly") and dl.months:
            for m in sorted(dl.months):
                y = year
                if m < month or (m == month and dl.day_of_month < today.day):
                    continue
                day = min(dl.day_of_month, self._last_day(y, m))
                return date(y, m, day)
            # Sljedeće godine
            m = dl.months[0]
            day = min(dl.day_of_month, self._last_day(year + 1, m))
            return date(year + 1, m, day)

        return None

    def _last_day(self, year: int, month: int) -> int:
        if month == 12: return 31
        return (date(year, month + 1, 1) - timedelta(days=1)).day

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_deadlines": len(self.deadlines),
            "upcoming_7_days": len(self.get_upcoming(7)),
        }
