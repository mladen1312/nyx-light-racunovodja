"""
Nyx Light — Modul D6: GFI XML Generator za FINA

Generira XML datoteku za elektroničku predaju godišnjih financijskih izvještaja
na RGFI (Registar godišnjih financijskih izvještaja) pri FINA.

Obrasci:
- BIL (Bilanca) — AOP 001-065
- RDG (Račun dobiti i gubitka) — AOP 100-170
- NTI (Novčani tokovi — indirektna metoda)
- PK (Promjene kapitala)
- Bilješke

Rokovi:
- Mikro/mali: 30. travnja
- Srednji/veliki: 30. lipnja (s revizorskim izvješćem)

Referenca: Pravilnik o strukturi i sadržaju GFI (NN 95/16)
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger("nyx_light.modules.gfi_xml")


class GFIXMLGenerator:
    """Generira XML za predaju na FINA RGFI."""

    def __init__(self):
        self._count = 0

    def generate(
        self,
        oib: str,
        naziv: str,
        godina: int,
        kategorija: str,  # mikro, mali, srednji, veliki
        bilanca: Dict[str, float],
        rdg: Dict[str, float],
        novcani_tokovi: Dict[str, float] = None,
        biljeske: str = "",
    ) -> Dict[str, Any]:
        """Generiraj GFI XML paket."""
        root = Element("GFI")
        root.set("xmlns", "http://rgfi.fina.hr/gfi")
        root.set("version", "2.0")

        # Zaglavlje
        header = SubElement(root, "Zaglavlje")
        SubElement(header, "OIB").text = oib
        SubElement(header, "Naziv").text = naziv
        SubElement(header, "Godina").text = str(godina)
        SubElement(header, "Kategorija").text = kategorija
        SubElement(header, "DatumPredaje").text = date.today().isoformat()

        rok = "30.04" if kategorija in ("mikro", "mali") else "30.06"
        SubElement(header, "Rok").text = f"{rok}.{godina + 1}"

        # BIL obrazac
        bil = SubElement(root, "Bilanca")
        self._add_bil_stavke(bil, bilanca)

        # RDG obrazac
        rdg_el = SubElement(root, "RDG")
        self._add_rdg_stavke(rdg_el, rdg)

        # NTI (ako postoji)
        if novcani_tokovi:
            nti = SubElement(root, "NovčaniTokovi")
            for key, val in novcani_tokovi.items():
                el = SubElement(nti, "Stavka")
                el.set("aop", key)
                el.text = f"{val:.2f}"

        # Bilješke
        if biljeske:
            bil_el = SubElement(root, "Biljeske")
            bil_el.text = biljeske

        xml_str = tostring(root, encoding="unicode", xml_declaration=False)
        xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

        self._count += 1

        return {
            "xml": xml_str,
            "filename": f"GFI_{oib}_{godina}.xml",
            "obrazci": self._list_obrazci(kategorija, novcani_tokovi),
            "rok": f"{rok}.{godina + 1}",
            "kategorija": kategorija,
            "predaja": "RGFI (rgfi.fina.hr)",
            "requires_approval": True,
            "napomena": "XML treba učitati na RGFI portal — računovođa predaje ručno",
        }

    def _add_bil_stavke(self, parent: Element, data: Dict[str, float]):
        """Dodaj BIL AOP stavke."""
        # Aktiva
        bil_aop = {
            "001": "Dugotrajna imovina",
            "002": "Nematerijalna imovina",
            "003": "Materijalna imovina",
            "010": "Financijska imovina",
            "020": "Kratkotrajna imovina",
            "021": "Zalihe",
            "022": "Potraživanja",
            "030": "Kratkotrajna financijska imovina",
            "031": "Novac",
            "040": "Ukupna aktiva",
            # Pasiva
            "050": "Kapital i rezerve",
            "051": "Temeljni kapital",
            "052": "Rezerve",
            "053": "Zadržana dobit/preneseni gubitak",
            "054": "Dobit/gubitak tekuće godine",
            "060": "Dugoročne obveze",
            "061": "Kratkoročne obveze",
            "065": "Ukupna pasiva",
        }

        for aop, opis in bil_aop.items():
            value = data.get(aop, data.get(opis, 0))
            el = SubElement(parent, "Stavka")
            el.set("aop", aop)
            el.set("opis", opis)
            el.text = f"{value:.2f}"

    def _add_rdg_stavke(self, parent: Element, data: Dict[str, float]):
        """Dodaj RDG AOP stavke."""
        rdg_aop = {
            "100": "Poslovni prihodi",
            "101": "Prihodi od prodaje",
            "110": "Poslovni rashodi",
            "111": "Materijalni troškovi",
            "112": "Troškovi osoblja",
            "113": "Amortizacija",
            "114": "Ostali troškovi",
            "120": "Financijski prihodi",
            "130": "Financijski rashodi",
            "140": "Ukupni prihodi",
            "150": "Ukupni rashodi",
            "160": "Dobit/gubitak prije oporezivanja",
            "161": "Porez na dobit",
            "170": "Dobit/gubitak razdoblja",
        }

        for aop, opis in rdg_aop.items():
            value = data.get(aop, data.get(opis, 0))
            el = SubElement(parent, "Stavka")
            el.set("aop", aop)
            el.set("opis", opis)
            el.text = f"{value:.2f}"

    def _list_obrazci(self, kategorija: str, nti: Dict = None) -> List[str]:
        """Obvezni obrasci prema kategoriji."""
        obrazci = ["BIL", "RDG"]
        if kategorija in ("srednji", "veliki"):
            obrazci.extend(["NTI", "PK", "Bilješke"])
        elif kategorija == "mali":
            obrazci.append("Bilješke")
        if nti:
            if "NTI" not in obrazci:
                obrazci.append("NTI")
        return obrazci

    def validate_balance(self, bilanca: Dict[str, float]) -> Dict[str, Any]:
        """Provjeri da aktiva = pasiva."""
        aktiva = bilanca.get("040", bilanca.get("Ukupna aktiva", 0))
        pasiva = bilanca.get("065", bilanca.get("Ukupna pasiva", 0))
        diff = abs(aktiva - pasiva)
        return {
            "aktiva": aktiva,
            "pasiva": pasiva,
            "razlika": round(diff, 2),
            "valid": diff < 0.01,
            "error": None if diff < 0.01 else f"⛔ Aktiva ({aktiva}) ≠ Pasiva ({pasiva}), razlika: {diff:.2f}",
        }

    def get_stats(self):
        return {"gfi_xml_generated": self._count}
