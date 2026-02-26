"""
Nyx Light — Modul A7: Osnovna sredstva i sitan inventar

Evidencija dugotrajne imovine, automatski obračun amortizacije,
praćenje korisnog vijeka i podsjetnici za inventuru.

Prag za dugotrajna imovina: 665,00 EUR (čl. 12. Pravilnika o amortizaciji)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.osnovna_sredstva")

# Prag za razvrstavanje: sitan inventar vs dugotrajna imovina
PRAG_DUGOTRAJNA_IMOVINA = 665.00  # EUR

# Stope amortizacije prema Pravilniku o amortizaciji (NN 1/01, izmjene)
AMORTIZACIJSKE_STOPE = {
    "građevinski_objekti": {"vijek": 20, "stopa": 5.0},
    "osobni_automobili": {"vijek": 5, "stopa": 20.0},
    "teretna_vozila": {"vijek": 4, "stopa": 25.0},
    "računalna_oprema": {"vijek": 2, "stopa": 50.0},
    "uredska_oprema": {"vijek": 4, "stopa": 25.0},
    "namjestaj": {"vijek": 5, "stopa": 20.0},
    "strojevi_oprema": {"vijek": 5, "stopa": 20.0},
    "software": {"vijek": 2, "stopa": 50.0},
    "licence_patenti": {"vijek": 4, "stopa": 25.0},
    "alati": {"vijek": 5, "stopa": 20.0},
    "telekomunikacijska_oprema": {"vijek": 5, "stopa": 20.0},
}


@dataclass
class FixedAsset:
    """Jedno osnovno sredstvo."""
    id: str = ""
    naziv: str = ""
    opis: str = ""
    vrsta: str = "uredska_oprema"
    nabavna_vrijednost: float = 0.0
    datum_nabave: str = ""
    datum_aktivacije: str = ""
    korisni_vijek_godina: int = 0
    godisnja_stopa: float = 0.0
    metoda: str = "linearna"     # linearna ili ubrzana
    ukupna_amortizacija: float = 0.0
    sadasnja_vrijednost: float = 0.0
    potpuno_amortizirano: bool = False
    rashod: bool = False
    konto_imovina: str = "0220"  # Oprema
    konto_ispravak: str = "0290"
    inventurni_broj: str = ""
    lokacija: str = ""


class OsnovnaSredstvaEngine:
    """Evidencija i amortizacija osnovnih sredstava."""

    def __init__(self):
        self._assets: Dict[str, FixedAsset] = {}
        self._asset_count = 0

    def add_asset(self, asset_data: Dict) -> Dict[str, Any]:
        """Dodaj novo osnovno sredstvo u evidenciju."""
        nabavna = asset_data.get("nabavna_vrijednost", 0)

        # Provjera praga
        if nabavna < PRAG_DUGOTRAJNA_IMOVINA:
            return {
                "status": "sitan_inventar",
                "message": (
                    f"Nabavna vrijednost ({nabavna:.2f} EUR) ispod praga "
                    f"za dugotrajnu imovinu ({PRAG_DUGOTRAJNA_IMOVINA:.2f} EUR). "
                    "Razvrstava se kao sitan inventar."
                ),
                "konto": "1020",  # Sitan inventar
                "jednokratni_otpis": True,
            }

        vrsta = asset_data.get("vrsta", "uredska_oprema")
        stopa_info = AMORTIZACIJSKE_STOPE.get(vrsta, {"vijek": 5, "stopa": 20.0})

        asset_id = f"OS-{self._asset_count + 1:04d}"
        asset = FixedAsset(
            id=asset_id,
            naziv=asset_data.get("naziv", ""),
            opis=asset_data.get("opis", ""),
            vrsta=vrsta,
            nabavna_vrijednost=nabavna,
            datum_nabave=asset_data.get("datum_nabave", datetime.now().strftime("%Y-%m-%d")),
            datum_aktivacije=asset_data.get("datum_aktivacije", ""),
            korisni_vijek_godina=asset_data.get("korisni_vijek", stopa_info["vijek"]),
            godisnja_stopa=asset_data.get("godisnja_stopa", stopa_info["stopa"]),
            sadasnja_vrijednost=nabavna,
            konto_imovina=self._get_konto_imovina(vrsta),
            inventurni_broj=asset_data.get("inventurni_broj", asset_id),
            lokacija=asset_data.get("lokacija", ""),
        )

        self._assets[asset_id] = asset
        self._asset_count += 1

        return {
            "status": "added",
            "id": asset_id,
            "naziv": asset.naziv,
            "nabavna_vrijednost": nabavna,
            "godisnja_stopa": asset.godisnja_stopa,
            "korisni_vijek": asset.korisni_vijek_godina,
            "godisnja_amortizacija": round(nabavna * asset.godisnja_stopa / 100, 2),
            "mjesecna_amortizacija": round(nabavna * asset.godisnja_stopa / 100 / 12, 2),
            "konto_imovina": asset.konto_imovina,
            "konto_ispravak": asset.konto_ispravak,
            "requires_approval": True,
        }

    def calculate_monthly_depreciation(self) -> List[Dict[str, Any]]:
        """Izračunaj mjesečnu amortizaciju za sva aktivna sredstva."""
        results = []
        for aid, asset in self._assets.items():
            if asset.potpuno_amortizirano or asset.rashod:
                continue

            mjesecna = round(
                asset.nabavna_vrijednost * asset.godisnja_stopa / 100 / 12, 2
            )

            # Ne prekorači nabavnu vrijednost
            preostalo = asset.nabavna_vrijednost - asset.ukupna_amortizacija
            if mjesecna > preostalo:
                mjesecna = round(preostalo, 2)

            if mjesecna <= 0:
                asset.potpuno_amortizirano = True
                continue

            results.append({
                "asset_id": aid,
                "naziv": asset.naziv,
                "mjesecna_amortizacija": mjesecna,
                "ukupna_dosad": asset.ukupna_amortizacija,
                "preostala_vrijednost": round(preostalo - mjesecna, 2),
                "konto_duguje": "5300",   # Trošak amortizacije
                "konto_potrazuje": asset.konto_ispravak,
            })

        return results

    def apply_depreciation(self, amounts: List[Dict]):
        """Primijeni amortizaciju (nakon odobrenja)."""
        for item in amounts:
            aid = item.get("asset_id")
            if aid in self._assets:
                self._assets[aid].ukupna_amortizacija += item["mjesecna_amortizacija"]
                self._assets[aid].sadasnja_vrijednost = round(
                    self._assets[aid].nabavna_vrijednost -
                    self._assets[aid].ukupna_amortizacija, 2
                )

    def get_inventura_list(self) -> List[Dict]:
        """Generiraj inventurnu listu za godišnji popis."""
        return [
            {
                "inventurni_broj": a.inventurni_broj,
                "naziv": a.naziv,
                "nabavna_vrijednost": a.nabavna_vrijednost,
                "ispravak": a.ukupna_amortizacija,
                "sadasnja_vrijednost": a.sadasnja_vrijednost,
                "lokacija": a.lokacija,
                "potpuno_amortizirano": a.potpuno_amortizirano,
                "stanje": "___________",  # Za fizičku provjeru
            }
            for a in self._assets.values()
            if not a.rashod
        ]

    def get_expiring_soon(self, months_ahead: int = 6) -> List[Dict]:
        """Sredstva kojima uskoro istječe korisni vijek."""
        results = []
        for a in self._assets.values():
            if a.potpuno_amortizirano or a.rashod:
                continue
            preostalo = a.nabavna_vrijednost - a.ukupna_amortizacija
            mjesecna = a.nabavna_vrijednost * a.godisnja_stopa / 100 / 12
            if mjesecna > 0:
                preostali_mjeseci = preostalo / mjesecna
                if preostali_mjeseci <= months_ahead:
                    results.append({
                        "id": a.id, "naziv": a.naziv,
                        "preostali_mjeseci": round(preostali_mjeseci, 1),
                        "preostala_vrijednost": round(preostalo, 2),
                    })
        return results

    def _get_konto_imovina(self, vrsta: str) -> str:
        konto_map = {
            "građevinski_objekti": "0210",
            "osobni_automobili": "0240",
            "teretna_vozila": "0240",
            "računalna_oprema": "0220",
            "uredska_oprema": "0230",
            "namjestaj": "0230",
            "strojevi_oprema": "0220",
            "software": "0120",
            "licence_patenti": "0100",
            "alati": "0230",
        }
        return konto_map.get(vrsta, "0220")

    def get_stats(self) -> Dict[str, Any]:
        active = [a for a in self._assets.values() if not a.rashod]
        return {
            "total_assets": len(self._assets),
            "active_assets": len(active),
            "total_value": round(sum(a.nabavna_vrijednost for a in active), 2),
            "total_depreciation": round(sum(a.ukupna_amortizacija for a in active), 2),
        }
