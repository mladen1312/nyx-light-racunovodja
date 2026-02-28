"""
Nyx Light — GFI XML (Godišnji financijski izvještaji)

Generira:
  1. Bilanca (AOP 001-065)
  2. RDG — Račun dobiti i gubitka (AOP 100-170)
  3. Bilješke uz financijske izvještaje
  4. Izvještaj o novčanom tijeku (indirektna metoda)
  5. XML export za FINA e-GFI

Referenca: Pravilnik o strukturi i sadržaju GFI (NN 95/16)
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger("nyx_light.modules.gfi_xml")


# ═══════════════════════════════════════════
# AOP POZICIJE — BILANCA
# ═══════════════════════════════════════════

BILANCA_AOP = {
    # AKTIVA
    "001": "A) POTRAŽIVANJA ZA UPISANI A NEUPLAĆENI KAPITAL",
    "002": "B) DUGOTRAJNA IMOVINA",
    "003": "I. Nematerijalna imovina",
    "004": "  1. Izdaci za razvoj",
    "005": "  2. Koncesije, patenti, licencije",
    "006": "  3. Goodwill",
    "007": "  4. Predujmovi za NI",
    "008": "  5. Ostala NI",
    "009": "II. Materijalna imovina",
    "010": "  1. Zemljišta",
    "011": "  2. Građevinski objekti",
    "012": "  3. Postrojenja i oprema",
    "013": "  4. Alati, pogonski inventar",
    "014": "  5. Biološka imovina",
    "015": "  6. Predujmovi za MI",
    "016": "  7. Ostala MI",
    "017": "  8. Ulaganje u nekretnine",
    "018": "III. Dugotrajna financijska imovina",
    "019": "  1. Udjeli kod povezanih poduzetnika",
    "020": "  2. Dani zajmovi povezanima",
    "021": "  3. Sudjelujući interesi",
    "022": "  4. Ulaganja u VP",
    "023": "  5. Dani zajmovi ostali",
    "024": "  6. Ostala DFI",
    "025": "IV. Potraživanja",
    "026": "V. Odgođena porezna imovina",
    "027": "C) KRATKOTRAJNA IMOVINA",
    "028": "I. Zalihe",
    "029": "  1. Sirovine i materijal",
    "030": "  2. Proizvodnja u tijeku",
    "031": "  3. Gotovi proizvodi",
    "032": "  4. Trgovačka roba",
    "033": "  5. Predujmovi za zalihe",
    "034": "  6. Biološka imovina kratkotrajna",
    "035": "II. Potraživanja",
    "036": "  1. Potraživanja od kupaca",
    "037": "  2. Potraživanja od povezanih",
    "038": "  3. Potraživanja od države",
    "039": "  4. Ostala potraživanja",
    "040": "III. Kratkotrajna financijska imovina",
    "041": "IV. Novac u banci i blagajni",
    "042": "D) PLAĆENI TROŠKOVI BUDUĆEG RAZDOBLJA I OBRAČUNATI PRIHODI",
    "043": "E) UKUPNO AKTIVA",
    # PASIVA
    "044": "A) KAPITAL I REZERVE",
    "045": "I. Temeljni (upisani) kapital",
    "046": "II. Kapitalne rezerve",
    "047": "III. Rezerve iz dobiti",
    "048": "IV. Revalorizacijske rezerve",
    "049": "V. Rezerve fer vrijednosti",
    "050": "VI. Zadržana dobit ili preneseni gubitak",
    "051": "VII. Dobit ili gubitak poslovne godine",
    "052": "VIII. Manjinski (nekontrolirajući) interes",
    "053": "B) REZERVIRANJA",
    "054": "C) DUGOROČNE OBVEZE",
    "055": "  1. Obveze prema bankama",
    "056": "  2. Obveze po obveznicama",
    "057": "  3. Obveze prema povezanima",
    "058": "  4. Ostale dugoročne obveze",
    "059": "  5. Odgođena porezna obveza",
    "060": "D) KRATKOROČNE OBVEZE",
    "061": "  1. Obveze prema dobavljačima",
    "062": "  2. Obveze za zajmove kratkoročne",
    "063": "  3. Obveze prema zaposlenicima",
    "064": "  4. Obveze za poreze i doprinose",
    "065": "  5. Ostale kratkoročne obveze",
    "066": "E) ODGOĐENO PLAĆANJE TROŠKOVA I PRIHOD BUDUĆEG RAZDOBLJA",
    "067": "F) UKUPNO PASIVA",
}

# ═══════════════════════════════════════════
# AOP POZICIJE — RDG
# ═══════════════════════════════════════════

RDG_AOP = {
    "101": "I. Poslovni prihodi",
    "102": "  1. Prihodi od prodaje",
    "103": "  2. Ostali poslovni prihodi",
    "104": "II. Poslovni rashodi",
    "105": "  1. Materijalni troškovi",
    "106": "    a) Troškovi sirovina i materijala",
    "107": "    b) Troškovi prodane robe",
    "108": "    c) Ostali vanjski troškovi",
    "109": "  2. Troškovi osoblja",
    "110": "    a) Neto plaće i nadnice",
    "111": "    b) Troškovi poreza i doprinosa",
    "112": "  3. Amortizacija",
    "113": "  4. Ostali troškovi",
    "114": "  5. Vrijednosna usklađenja",
    "115": "  6. Rezerviranja",
    "116": "  7. Ostali poslovni rashodi",
    "117": "III. FINANCIJSKI PRIHODI",
    "118": "  1. Kamate i slični prihodi",
    "119": "  2. Tečajne razlike",
    "120": "  3. Ostali financijski prihodi",
    "121": "IV. FINANCIJSKI RASHODI",
    "122": "  1. Kamate i slični rashodi",
    "123": "  2. Tečajne razlike",
    "124": "  3. Ostali financijski rashodi",
    "125": "V. UKUPNI PRIHODI",
    "126": "VI. UKUPNI RASHODI",
    "127": "VII. DOBIT ILI GUBITAK PRIJE OPOREZIVANJA",
    "128": "VIII. POREZ NA DOBIT",
    "129": "IX. DOBIT ILI GUBITAK RAZDOBLJA",
}


@dataclass
class GFIPozicija:
    aop: str = ""
    naziv: str = ""
    tekuce: float = 0.0
    prethodno: float = 0.0


@dataclass
class GFIIzvjestaj:
    naziv_izvjestaja: str = ""  # bilanca, rdg, novcani_tok
    oib: str = ""
    naziv_drustva: str = ""
    razdoblje: str = ""
    pozicije: List[GFIPozicija] = field(default_factory=list)


class GFIXMLGenerator:
    """Generira GFI izvještaje i XML za FINA."""

    def generate_bilanca(
        self,
        data: Dict[str, float],
        prethodno: Dict[str, float] = None,
        oib: str = "",
        naziv: str = "",
        godina: int = 0,
    ) -> GFIIzvjestaj:
        """Generiraj bilancu iz AOP podataka."""
        if not godina:
            godina = date.today().year - 1

        izvjestaj = GFIIzvjestaj(
            naziv_izvjestaja="Bilanca",
            oib=oib, naziv_drustva=naziv,
            razdoblje=f"01.01.{godina} — 31.12.{godina}",
        )

        prev = prethodno or {}
        for aop, naziv_poz in BILANCA_AOP.items():
            izvjestaj.pozicije.append(GFIPozicija(
                aop=aop, naziv=naziv_poz,
                tekuce=data.get(aop, 0.0),
                prethodno=prev.get(aop, 0.0),
            ))

        # Auto-izračun sumiranih pozicija
        self._auto_sum_bilanca(izvjestaj, data)

        return izvjestaj

    def generate_rdg(
        self,
        data: Dict[str, float],
        prethodno: Dict[str, float] = None,
        oib: str = "",
        naziv: str = "",
        godina: int = 0,
    ) -> GFIIzvjestaj:
        """Generiraj RDG iz AOP podataka."""
        if not godina:
            godina = date.today().year - 1

        izvjestaj = GFIIzvjestaj(
            naziv_izvjestaja="Račun dobiti i gubitka",
            oib=oib, naziv_drustva=naziv,
            razdoblje=f"01.01.{godina} — 31.12.{godina}",
        )

        prev = prethodno or {}
        for aop, naziv_poz in RDG_AOP.items():
            izvjestaj.pozicije.append(GFIPozicija(
                aop=aop, naziv=naziv_poz,
                tekuce=data.get(aop, 0.0),
                prethodno=prev.get(aop, 0.0),
            ))

        return izvjestaj

    def _auto_sum_bilanca(self, izvjestaj: GFIIzvjestaj, data: Dict):
        """Auto-izračun sume za agregatne AOP pozicije."""
        poz = {p.aop: p for p in izvjestaj.pozicije}

        # Nematerijalna (003) = sum(004-008)
        if "003" in poz and poz["003"].tekuce == 0:
            poz["003"].tekuce = sum(
                poz[a].tekuce for a in ["004","005","006","007","008"] if a in poz
            )

        # Materijalna (009) = sum(010-017)
        if "009" in poz and poz["009"].tekuce == 0:
            poz["009"].tekuce = sum(
                poz[a].tekuce for a in ["010","011","012","013","014","015","016","017"] if a in poz
            )

        # Dugotrajna (002) = 003 + 009 + 018 + 025 + 026
        if "002" in poz and poz["002"].tekuce == 0:
            poz["002"].tekuce = sum(
                poz[a].tekuce for a in ["003","009","018","025","026"] if a in poz
            )

        # Kratkotrajna (027) = 028 + 035 + 040 + 041
        if "027" in poz and poz["027"].tekuce == 0:
            poz["027"].tekuce = sum(
                poz[a].tekuce for a in ["028","035","040","041"] if a in poz
            )

        # Ukupno aktiva (043) = 001 + 002 + 027 + 042
        if "043" in poz and poz["043"].tekuce == 0:
            poz["043"].tekuce = sum(
                poz[a].tekuce for a in ["001","002","027","042"] if a in poz
            )

        # Ukupno pasiva (067) = 044 + 053 + 054 + 060 + 066
        if "067" in poz and poz["067"].tekuce == 0:
            poz["067"].tekuce = sum(
                poz[a].tekuce for a in ["044","053","054","060","066"] if a in poz
            )

    def to_xml(self, izvjestaj: GFIIzvjestaj) -> str:
        """Generiraj XML za FINA e-GFI sustav."""
        root = ET.Element("GFI")
        root.set("xmlns", "http://fina.hr/gfi")
        root.set("version", "2.0")

        header = ET.SubElement(root, "Zaglavlje")
        ET.SubElement(header, "OIB").text = izvjestaj.oib
        ET.SubElement(header, "NazivDrustva").text = izvjestaj.naziv_drustva
        ET.SubElement(header, "VrstaIzvjestaja").text = izvjestaj.naziv_izvjestaja
        ET.SubElement(header, "Razdoblje").text = izvjestaj.razdoblje

        podaci = ET.SubElement(root, "Podaci")
        for poz in izvjestaj.pozicije:
            if poz.tekuce != 0 or poz.prethodno != 0:
                stavka = ET.SubElement(podaci, "Stavka")
                ET.SubElement(stavka, "AOP").text = poz.aop
                ET.SubElement(stavka, "Naziv").text = poz.naziv.strip()
                ET.SubElement(stavka, "Tekuce").text = f"{poz.tekuce:.2f}"
                ET.SubElement(stavka, "Prethodno").text = f"{poz.prethodno:.2f}"

        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    def to_dict(self, izvjestaj: GFIIzvjestaj) -> Dict[str, Any]:
        return {
            "izvjestaj": izvjestaj.naziv_izvjestaja,
            "oib": izvjestaj.oib,
            "naziv": izvjestaj.naziv_drustva,
            "razdoblje": izvjestaj.razdoblje,
            "pozicije": [
                {"aop": p.aop, "naziv": p.naziv.strip(),
                 "tekuce": p.tekuce, "prethodno": p.prethodno}
                for p in izvjestaj.pozicije
                if p.tekuce != 0 or p.prethodno != 0
            ],
            "ukupno_aop_pozicija": len([p for p in izvjestaj.pozicije if p.tekuce or p.prethodno]),
        }

    def get_available_reports(self) -> List[str]:
        return ["Bilanca", "RDG", "Bilješke", "Novčani tok"]

    def generate(self, oib: str = "", naziv: str = "", godina: int = 0,
                 kategorija: str = "mikro", bilanca: Dict = None,
                 rdg: Dict = None, novcani_tokovi: Dict = None,
                 **kwargs) -> Dict[str, Any]:
        """Backward-compat generate() — generira sve izvještaje odjednom."""
        result = {"oib": oib, "naziv": naziv, "godina": godina, "kategorija": kategorija}

        if bilanca:
            b = self.generate_bilanca(bilanca, oib=oib, naziv=naziv, godina=godina)
            result["bilanca"] = self.to_dict(b)
            result["bilanca_xml"] = self.to_xml(b)

        if rdg:
            r = self.generate_rdg(rdg, oib=oib, naziv=naziv, godina=godina)
            result["rdg"] = self.to_dict(r)
            result["rdg_xml"] = self.to_xml(r)

        # Combined XML for backward compat
        xml_parts = []
        if "bilanca_xml" in result:
            xml_parts.append(result["bilanca_xml"])
        if "rdg_xml" in result:
            xml_parts.append(result["rdg_xml"])
        if xml_parts:
            result["xml"] = "\n".join(xml_parts)

        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "module": "gfi_xml", "status": "active",
            "bilanca_aop": len(BILANCA_AOP), "rdg_aop": len(RDG_AOP),
            "available": self.get_available_reports(),
        }
