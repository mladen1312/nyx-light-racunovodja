"""
Nyx Light — Modul B5: Kadrovska evidencija

Centralni registar zaposlenika za potrebe obračuna plaća i JOPPD-a.
Prati: osobne podatke, ugovore, godišnje odmore, bolovanja, staž.

OVO NIJE HR sustav — to je minimum koji računovođa treba za obračun.

Referenca:
- Zakon o radu (NN 93/14, ... 64/23)
- Pravilnik o sadržaju i načinu vođenja evidencije o radnicima (NN 73/17)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.kadrovska")

# Minimalne zakonske obveze
MIN_GODISNJI_ODMOR_DANI = 20  # čl. 77. ZoR — minimum 4 tjedna
MIN_PLACA_2026 = 970.0  # EUR bruto


@dataclass
class Zaposlenik:
    """Podaci o zaposleniku relevantni za računovodstvo."""
    id: str = ""
    ime: str = ""
    prezime: str = ""
    oib: str = ""
    datum_rodenja: str = ""  # YYYY-MM-DD
    adresa: str = ""
    grad: str = "Zagreb"

    # Ugovor
    datum_zaposlenja: str = ""
    vrsta_ugovora: str = "neodredeno"  # neodredeno, odredeno, probni
    radno_mjesto: str = ""
    bruto_placa: float = 0.0
    sati_tjedno: float = 40.0

    # Porezno
    osobni_odbitak_faktor: float = 1.0  # 1.0 = osnovni
    broj_djece: int = 0
    broj_uzdrzavanih: int = 0
    olaksica_mladi: bool = False
    invalidnost: bool = False

    # Godišnji odmor
    pravo_na_godisnji: int = MIN_GODISNJI_ODMOR_DANI
    iskoristeno_godisnji: int = 0
    preneseno_prosla_godina: int = 0

    # Status
    aktivan: bool = True
    datum_prestanka: str = ""
    razlog_prestanka: str = ""


class KadrovskaEvidencija:
    """Registar zaposlenika."""

    def __init__(self):
        self._zaposlenici: Dict[str, Zaposlenik] = {}
        self._bolovanja: List[Dict] = []

    def add(self, z: Zaposlenik) -> Dict[str, Any]:
        """Dodaj zaposlenika."""
        errors = self._validate(z)
        if errors:
            return {"success": False, "errors": errors}

        self._zaposlenici[z.id] = z
        return {"success": True, "id": z.id, "ime": f"{z.ime} {z.prezime}"}

    def get(self, zap_id: str) -> Optional[Zaposlenik]:
        return self._zaposlenici.get(zap_id)

    def list_active(self) -> List[Zaposlenik]:
        return [z for z in self._zaposlenici.values() if z.aktivan]

    def list_all(self) -> List[Zaposlenik]:
        return list(self._zaposlenici.values())

    def deactivate(self, zap_id: str, datum: str, razlog: str = "") -> Dict:
        z = self._zaposlenici.get(zap_id)
        if not z:
            return {"success": False, "error": "Zaposlenik nije pronađen"}
        z.aktivan = False
        z.datum_prestanka = datum
        z.razlog_prestanka = razlog
        return {"success": True, "id": zap_id}

    def record_godisnji(self, zap_id: str, dani: int) -> Dict:
        """Evidentiraj korištenje godišnjeg odmora."""
        z = self._zaposlenici.get(zap_id)
        if not z:
            return {"success": False, "error": "Zaposlenik nije pronađen"}

        raspolozivo = z.pravo_na_godisnji + z.preneseno_prosla_godina - z.iskoristeno_godisnji
        warnings = []
        if dani > raspolozivo:
            warnings.append(
                f"⚠️ Traži {dani} dana, raspoloživo samo {raspolozivo}. "
                "Preostali dani idu na neplaćeni dopust."
            )

        z.iskoristeno_godisnji += dani
        return {
            "success": True,
            "iskoristeno": z.iskoristeno_godisnji,
            "preostalo": max(0, raspolozivo - dani),
            "warnings": warnings,
        }

    def godisnji_pregled(self) -> List[Dict]:
        """Pregled godišnjih odmora svih aktivnih zaposlenika."""
        result = []
        for z in self.list_active():
            raspolozivo = z.pravo_na_godisnji + z.preneseno_prosla_godina
            result.append({
                "id": z.id,
                "ime": f"{z.ime} {z.prezime}",
                "pravo": z.pravo_na_godisnji,
                "preneseno": z.preneseno_prosla_godina,
                "iskoristeno": z.iskoristeno_godisnji,
                "preostalo": raspolozivo - z.iskoristeno_godisnji,
            })
        return result

    def payroll_data(self, zap_id: str) -> Optional[Dict]:
        """Podaci potrebni za obračun plaće."""
        z = self._zaposlenici.get(zap_id)
        if not z:
            return None
        return {
            "oib": z.oib,
            "ime": z.ime,
            "prezime": z.prezime,
            "bruto": z.bruto_placa,
            "osobni_odbitak_faktor": z.osobni_odbitak_faktor,
            "broj_djece": z.broj_djece,
            "broj_uzdrzavanih": z.broj_uzdrzavanih,
            "olaksica_mladi": z.olaksica_mladi,
            "invalidnost": z.invalidnost,
            "grad": z.grad,
        }

    def staz_report(self) -> List[Dict]:
        """Izvještaj o stažu zaposlenika."""
        today = date.today()
        result = []
        for z in self.list_active():
            if z.datum_zaposlenja:
                start = date.fromisoformat(z.datum_zaposlenja)
                staz = (today - start).days
                godina = staz // 365
                mjeseci = (staz % 365) // 30
            else:
                godina = mjeseci = 0
            result.append({
                "id": z.id, "ime": f"{z.ime} {z.prezime}",
                "od": z.datum_zaposlenja,
                "staz_godina": godina, "staz_mjeseci": mjeseci,
                "vrsta_ugovora": z.vrsta_ugovora,
            })
        return result

    def _validate(self, z: Zaposlenik) -> List[str]:
        errors = []
        if not z.id:
            errors.append("ID zaposlenika je obavezan")
        if not z.oib or len(z.oib) != 11:
            errors.append("OIB mora imati 11 znamenki")
        if z.bruto_placa < MIN_PLACA_2026 and z.bruto_placa > 0:
            errors.append(f"Bruto plaća ({z.bruto_placa}) ispod minimalne ({MIN_PLACA_2026} EUR)")
        if z.pravo_na_godisnji < MIN_GODISNJI_ODMOR_DANI:
            errors.append(f"Godišnji odmor ne može biti ispod {MIN_GODISNJI_ODMOR_DANI} dana")
        return errors

    def get_stats(self):
        active = len(self.list_active())
        total = len(self._zaposlenici)
        return {"active": active, "total": total}
