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
