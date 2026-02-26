"""
Nyx Light — Registar klijenata

Svaki klijent ureda ima:
- ERP sustav (CPP, Synesis, eRacuni, Pantheon)
- PDV status (mjesečni/tromjesečni)
- Kategorija poduzetnika (mikro/mali/srednji/veliki)
- Kontni plan varijacije

Ovo je centralno mjesto koje govori Pipeline-u KAMO slati podatke.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.registry")


@dataclass
class ClientConfig:
    """Konfiguracija jednog klijenta."""
    id: str = ""
    naziv: str = ""
    oib: str = ""
    erp_target: str = "CPP"           # CPP, Synesis, eRacuni, Pantheon
    erp_export_format: str = "XML"    # XML, CSV, JSON
    pdv_obveznik: bool = True
    pdv_period: str = "monthly"       # monthly / quarterly
    kategorija: str = "mikro"         # mikro, mali, srednji, veliki
    standardi: str = "HSFI"           # HSFI / MSFI
    djelatnost: str = ""              # NKD šifra
    grad: str = "Zagreb"              # Za prirez
    active: bool = True

    # Specifičnosti
    kontni_plan_varijacija: str = ""  # Ako klijent koristi nestandardne konte
    ima_robno: bool = False           # Robno-materijalno poslovanje
    ima_place: bool = True            # Obračun plaća
    ima_os: bool = True               # Osnovna sredstva
    napomena: str = ""


class ClientRegistry:
    """Registar svih klijenata ureda."""

    def __init__(self):
        self._clients: Dict[str, ClientConfig] = {}

    def register(self, config: ClientConfig) -> Dict[str, Any]:
        """Registriraj novog klijenta."""
        self._clients[config.id] = config
        logger.info("Klijent registriran: %s (%s → %s %s)",
                     config.naziv, config.id, config.erp_target, config.erp_export_format)
        return {"id": config.id, "erp": config.erp_target, "status": "registered"}

    def get(self, client_id: str) -> Optional[ClientConfig]:
        return self._clients.get(client_id)

    def get_erp_target(self, client_id: str) -> str:
        """Dohvati ERP sustav za klijenta."""
        c = self._clients.get(client_id)
        return c.erp_target if c else "CPP"

    def get_export_format(self, client_id: str) -> str:
        c = self._clients.get(client_id)
        return c.erp_export_format if c else "XML"

    def list_by_erp(self, erp: str) -> List[ClientConfig]:
        """Dohvati sve klijente za dani ERP."""
        return [c for c in self._clients.values() if c.erp_target == erp and c.active]

    def list_pdv_monthly(self) -> List[ClientConfig]:
        """Klijenti s mjesečnom PDV prijavom."""
        return [c for c in self._clients.values()
                if c.pdv_obveznik and c.pdv_period == "monthly" and c.active]

    def list_pdv_quarterly(self) -> List[ClientConfig]:
        return [c for c in self._clients.values()
                if c.pdv_obveznik and c.pdv_period == "quarterly" and c.active]

    def list_all(self, active_only: bool = True) -> List[ClientConfig]:
        if active_only:
            return [c for c in self._clients.values() if c.active]
        return list(self._clients.values())

    def get_stats(self) -> Dict[str, Any]:
        active = [c for c in self._clients.values() if c.active]
        erp_counts = {}
        for c in active:
            erp_counts[c.erp_target] = erp_counts.get(c.erp_target, 0) + 1
        return {
            "total": len(self._clients),
            "active": len(active),
            "by_erp": erp_counts,
            "pdv_monthly": len(self.list_pdv_monthly()),
            "pdv_quarterly": len(self.list_pdv_quarterly()),
        }
