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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Klijent-specifični rokovi, obavijesti, kazne
# ════════════════════════════════════════════════════════

# Kazne za kašnjenje s prijavama
KAZNE = {
    "PDV prijava (mjesečna)": {
        "kazna_min": 2000.0, "kazna_max": 20000.0,
        "zakonski_temelj": "čl. 186 ZPDV",
    },
    "JOPPD obrazac": {
        "kazna_min": 1000.0, "kazna_max": 50000.0,
        "zakonski_temelj": "čl. 91 Zakona o porezu na dohodak",
    },
    "Porez na dobit (PD obrazac)": {
        "kazna_min": 2000.0, "kazna_max": 20000.0,
        "zakonski_temelj": "čl. 40 Zakona o porezu na dobit",
    },
    "GFI predaja FINA — standardni": {
        "kazna_min": 1000.0, "kazna_max": 10000.0,
        "zakonski_temelj": "čl. 44 Zakona o računovodstvu",
    },
}


class ClientDeadlineManager:
    """Upravljanje rokovima po klijentima."""

    def __init__(self):
        self._client_overrides = {}   # {client_id: {deadline_name: custom_date}}
        self._completed = {}          # {client_id: {deadline_name: completed_date}}

    def set_client_deadline(self, client_id: str, deadline_name: str, custom_date: str):
        """Postavi klijent-specifični rok (npr. tromjesečni PDV umjesto mjesečnog)."""
        if client_id not in self._client_overrides:
            self._client_overrides[client_id] = {}
        self._client_overrides[client_id][deadline_name] = custom_date

    def mark_completed(self, client_id: str, deadline_name: str, completed_date: str):
        """Označi rok kao ispunjen za klijenta."""
        if client_id not in self._completed:
            self._completed[client_id] = {}
        self._completed[client_id][deadline_name] = completed_date

    def get_client_status(self, client_id: str, tracker: DeadlineTracker = None) -> List[Dict]:
        """Status svih rokova za jednog klijenta."""
        tracker = tracker or DeadlineTracker()
        upcoming = tracker.get_upcoming(days_ahead=30)
        completed = self._completed.get(client_id, {})

        result = []
        for dl in upcoming:
            name = dl["name"]
            is_done = name in completed
            kazna = KAZNE.get(name, {})
            result.append({
                **dl,
                "client_id": client_id,
                "completed": is_done,
                "completed_date": completed.get(name, ""),
                "kazna_min": kazna.get("kazna_min", 0),
                "kazna_max": kazna.get("kazna_max", 0),
                "zakonski_temelj": kazna.get("zakonski_temelj", ""),
            })
        return result

    def get_all_overdue(self, client_ids: List[str], tracker: DeadlineTracker = None) -> List[Dict]:
        """Dohvati sve prekoračene rokove za sve klijente."""
        from datetime import date
        tracker = tracker or DeadlineTracker()
        today = date.today()
        overdue = []

        for cid in client_ids:
            completed = self._completed.get(cid, {})
            for dl in tracker.deadlines:
                next_date = tracker._next_occurrence(dl, today)
                if next_date and next_date < today:
                    if dl.name not in completed:
                        days_late = (today - next_date).days
                        kazna = KAZNE.get(dl.name, {})
                        overdue.append({
                            "client_id": cid,
                            "deadline": dl.name,
                            "due_date": next_date.isoformat(),
                            "days_late": days_late,
                            "kazna_min": kazna.get("kazna_min", 0),
                            "severity": "critical" if days_late > 15 else "warning",
                        })
        return sorted(overdue, key=lambda x: x["days_late"], reverse=True)


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Penalty info, klijent-specifični rokovi, obavijest scheduling
# ════════════════════════════════════════════════════════

KAZNE_KASNJENJE = {
    "PDV prijava (mjesečna)": {
        "kazna_min": 2000, "kazna_max": 20000,
        "zatezna_kamata": True,
        "napomena": "Čl. 116 ZPDV — prekršajna odgovornost za nepravodobnu predaju",
    },
    "JOPPD obrazac": {
        "kazna_min": 500, "kazna_max": 5000,
        "zatezna_kamata": False,
        "napomena": "Čl. 87 Zakona o porezu na dohodak",
    },
    "Porez na dobit (PD obrazac)": {
        "kazna_min": 2000, "kazna_max": 20000,
        "zatezna_kamata": True,
        "napomena": "Čl. 40 Zakona o porezu na dobit",
    },
    "GFI predaja FINA — standardni": {
        "kazna_min": 1000, "kazna_max": 10000,
        "zatezna_kamata": False,
        "napomena": "Čl. 42 Zakona o računovodstvu",
    },
}


class DeadlineNotifier:
    """Upravljanje obavijestima o rokovima."""

    NOTIFICATION_DAYS = [14, 7, 3, 1, 0]  # Dana prije roka

    def __init__(self, tracker: DeadlineTracker = None):
        self.tracker = tracker or DeadlineTracker()

    def get_notifications(self, today: date = None) -> List[Dict]:
        """Generiraj obavijesti za sve bliske rokove."""
        today = today or date.today()
        notifications = []

        for days_before in self.NOTIFICATION_DAYS:
            upcoming = self.tracker.get_upcoming(days_ahead=days_before + 1, today=today)
            for item in upcoming:
                if item["days_left"] == days_before:
                    penalty = KAZNE_KASNJENJE.get(item["name"], {})
                    notifications.append({
                        **item,
                        "notification_type": (
                            "critical" if days_before <= 1
                            else "warning" if days_before <= 3
                            else "reminder"
                        ),
                        "kazna_min": penalty.get("kazna_min", 0),
                        "kazna_max": penalty.get("kazna_max", 0),
                        "penalty_note": penalty.get("napomena", ""),
                    })

        return sorted(notifications, key=lambda x: x["days_left"])

    def get_client_deadlines(
        self,
        pdv_mjesecna: bool = True,
        intrastat_obveza: bool = False,
        revizijski_obveznik: bool = False,
    ) -> List[Dict]:
        """Filtrirani rokovi za specifičnog klijenta."""
        all_deadlines = self.tracker.get_upcoming(days_ahead=60)
        filtered = []
        for dl in all_deadlines:
            name = dl["name"]
            # Filtriraj PDV
            if "tromjesečna" in name and pdv_mjesecna:
                continue
            if "mjesečna" in name and not pdv_mjesecna:
                continue
            # Filtriraj Intrastat
            if "Intrastat" in name and not intrastat_obveza:
                continue
            # Filtriraj reviziju
            if "revizija" in name and not revizijski_obveznik:
                continue
            filtered.append(dl)
        return filtered
