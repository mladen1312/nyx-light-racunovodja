"""
Nyx Light — JOPPD Obrazac Generator

Generira strukturu JOPPD obrasca za predaju na ePorezna.
JOPPD se predaje na dan isplate plaće ili najkasnije do 15. sljedećeg mjeseca.

Format: XML prema shemi Porezne uprave RH.
Ovaj modul PRIPREMA podatke — konačna predaja je na računovođi.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.dom import minidom

logger = logging.getLogger("nyx_light.modules.joppd")


@dataclass
class JOPPDStavka:
    """Jedna stavka JOPPD obrasca (jedan radnik/primatelj)."""
    redni_broj: int = 0
    oib_primatelja: str = ""
    ime_prezime: str = ""
    oznaka_stjecatelja: str = "0001"  # 0001 = radnik (nesamostalni rad)
    oznaka_primitka: str = "0001"     # 0001 = plaća
    
    # Iznosi
    bruto: float = 0.0
    mio_stup_1: float = 0.0
    mio_stup_2: float = 0.0
    dohodak: float = 0.0
    osobni_odbitak: float = 0.0
    porezna_osnovica: float = 0.0
    porez: float = 0.0
    prirez: float = 0.0
    neto: float = 0.0
    
    # Olakšice
    olaksica_mladi_pct: float = 0.0
    olaksica_iznos: float = 0.0
    
    # Doprinosi na plaću
    zdravstveno: float = 0.0
    
    # Period
    datum_od: str = ""
    datum_do: str = ""
    sati_rada: int = 0


@dataclass
class JOPPDObrazac:
    """Kompletni JOPPD obrazac."""
    oznaka: str = ""           # Format: GGGG-MMM (npr. 2026-002 = veljača)
    datum_predaje: str = ""
    datum_isplate: str = ""
    oib_obveznika: str = ""    # OIB poslodavca
    naziv_obveznika: str = ""
    stavke: List[JOPPDStavka] = field(default_factory=list)
    
    # Ukupni iznosi (automatski izračunati)
    ukupno_bruto: float = 0.0
    ukupno_mio_1: float = 0.0
    ukupno_mio_2: float = 0.0
    ukupno_porez: float = 0.0
    ukupno_prirez: float = 0.0
    ukupno_neto: float = 0.0
    ukupno_zdravstveno: float = 0.0


OZNAKE_STJECATELJA = {
    "0001": "Radnik — nesamostalni rad",
    "0002": "Umirovljenik koji radi",
    "0004": "Osoba na stručnom osposobljavanju",
    "0011": "Autorski honorar",
    "0012": "Ugovor o djelu",
    "0021": "Dividenda",
    "0022": "Kamata",
}

OZNAKE_PRIMITKA = {
    "0001": "Plaća",
    "0002": "Plaća u naravi",
    "0004": "Bolovanje na teret poslodavca",
    "0008": "Bolovanje na teret HZZO",
    "0012": "Jubilarna nagrada",
    "0021": "Autorski honorar",
    "0031": "Ugovor o djelu",
    "0061": "Dividenda",
}


class JOPPDGenerator:
    """Generira JOPPD obrazac iz payroll rezultata."""

    def __init__(self):
        self._generation_count = 0

    def from_payroll_results(
        self,
        payroll_results: List,
        oib_poslodavca: str,
        naziv_poslodavca: str,
        datum_isplate: str = "",
        period_month: int = 0,
        period_year: int = 0,
    ) -> JOPPDObrazac:
        """Generiraj JOPPD iz liste payroll rezultata."""
        now = datetime.now()
        month = period_month or now.month
        year = period_year or now.year

        obrazac = JOPPDObrazac(
            oznaka=f"{year}-{month:03d}",
            datum_predaje=now.strftime("%Y-%m-%d"),
            datum_isplate=datum_isplate or now.strftime("%Y-%m-%d"),
            oib_obveznika=oib_poslodavca,
            naziv_obveznika=naziv_poslodavca,
        )

        for i, pr in enumerate(payroll_results, 1):
            stavka = JOPPDStavka(
                redni_broj=i,
                oib_primatelja=getattr(pr, "oib", "") if hasattr(pr, "oib") else "",
                ime_prezime=pr.employee_name,
                bruto=pr.bruto_placa,
                mio_stup_1=pr.mio_stup_1,
                mio_stup_2=pr.mio_stup_2,
                dohodak=pr.dohodak,
                osobni_odbitak=pr.osobni_odbitak,
                porezna_osnovica=pr.porezna_osnovica,
                porez=pr.porez,
                prirez=pr.prirez,
                neto=pr.neto_placa,
                olaksica_mladi_pct=pr.olaksica_mladi_pct,
                olaksica_iznos=pr.olaksica_iznos,
                zdravstveno=pr.zdravstveno,
                datum_od=f"{year}-{month:02d}-01",
                datum_do=f"{year}-{month:02d}-28",
            )
            obrazac.stavke.append(stavka)

        # Ukupni iznosi
        obrazac.ukupno_bruto = round(sum(s.bruto for s in obrazac.stavke), 2)
        obrazac.ukupno_mio_1 = round(sum(s.mio_stup_1 for s in obrazac.stavke), 2)
        obrazac.ukupno_mio_2 = round(sum(s.mio_stup_2 for s in obrazac.stavke), 2)
        obrazac.ukupno_porez = round(sum(s.porez for s in obrazac.stavke), 2)
        obrazac.ukupno_prirez = round(sum(s.prirez for s in obrazac.stavke), 2)
        obrazac.ukupno_neto = round(sum(s.neto for s in obrazac.stavke), 2)
        obrazac.ukupno_zdravstveno = round(sum(s.zdravstveno for s in obrazac.stavke), 2)

        self._generation_count += 1
        return obrazac

    def to_xml(self, obrazac: JOPPDObrazac) -> str:
        """Generiraj XML format za predaju na ePorezna."""
        root = ET.Element("JOPPD")
        root.set("xmlns", "http://e-porezna.porezna-uprava.hr/sheme/zahtjevi/JOPPD/v1.5")

        # Zaglavlje
        zag = ET.SubElement(root, "Zaglavlje")
        ET.SubElement(zag, "OznakaIzvjesca").text = obrazac.oznaka
        ET.SubElement(zag, "VrstaIzvjesca").text = "1"  # 1 = Izvorni
        ET.SubElement(zag, "DatumPodnosenja").text = obrazac.datum_predaje
        ET.SubElement(zag, "DatumIsplate").text = obrazac.datum_isplate

        podnositelj = ET.SubElement(zag, "Podnositelj")
        ET.SubElement(podnositelj, "OIB").text = obrazac.oib_obveznika
        ET.SubElement(podnositelj, "Naziv").text = obrazac.naziv_obveznika

        # Stavke (Stranica B)
        stranica_b = ET.SubElement(root, "StranicaB")
        for s in obrazac.stavke:
            st = ET.SubElement(stranica_b, "Stavka")
            ET.SubElement(st, "RedniBroj").text = str(s.redni_broj)
            ET.SubElement(st, "OIBStjecatelja").text = s.oib_primatelja
            ET.SubElement(st, "ImePrezime").text = s.ime_prezime
            ET.SubElement(st, "OznakaStjecatelja").text = s.oznaka_stjecatelja
            ET.SubElement(st, "OznakaPrimitka").text = s.oznaka_primitka
            ET.SubElement(st, "BrutoIznos").text = f"{s.bruto:.2f}"
            ET.SubElement(st, "MIO1").text = f"{s.mio_stup_1:.2f}"
            ET.SubElement(st, "MIO2").text = f"{s.mio_stup_2:.2f}"
            ET.SubElement(st, "Dohodak").text = f"{s.dohodak:.2f}"
            ET.SubElement(st, "OsobniOdbitak").text = f"{s.osobni_odbitak:.2f}"
            ET.SubElement(st, "PoreznaOsnovica").text = f"{s.porezna_osnovica:.2f}"
            ET.SubElement(st, "Porez").text = f"{s.porez:.2f}"
            ET.SubElement(st, "Prirez").text = f"{s.prirez:.2f}"
            ET.SubElement(st, "Neto").text = f"{s.neto:.2f}"
            ET.SubElement(st, "Zdravstveno").text = f"{s.zdravstveno:.2f}"
            ET.SubElement(st, "DatumOd").text = s.datum_od
            ET.SubElement(st, "DatumDo").text = s.datum_do

            if s.olaksica_mladi_pct > 0:
                ET.SubElement(st, "OlaksicaMladi").text = f"{s.olaksica_iznos:.2f}"

        # Ukupno
        ukupno = ET.SubElement(root, "Ukupno")
        ET.SubElement(ukupno, "UkupnoBruto").text = f"{obrazac.ukupno_bruto:.2f}"
        ET.SubElement(ukupno, "UkupnoMIO1").text = f"{obrazac.ukupno_mio_1:.2f}"
        ET.SubElement(ukupno, "UkupnoMIO2").text = f"{obrazac.ukupno_mio_2:.2f}"
        ET.SubElement(ukupno, "UkupnoPorez").text = f"{obrazac.ukupno_porez:.2f}"
        ET.SubElement(ukupno, "UkupnoPrirez").text = f"{obrazac.ukupno_prirez:.2f}"
        ET.SubElement(ukupno, "UkupnoNeto").text = f"{obrazac.ukupno_neto:.2f}"
        ET.SubElement(ukupno, "UkupnoZdravstveno").text = f"{obrazac.ukupno_zdravstveno:.2f}"

        return minidom.parseString(
            ET.tostring(root, encoding="unicode")
        ).toprettyxml(indent="  ")

    def to_dict(self, obrazac: JOPPDObrazac) -> Dict[str, Any]:
        """Pretvori u dict za pregled/API."""
        return {
            "oznaka": obrazac.oznaka,
            "datum_predaje": obrazac.datum_predaje,
            "datum_isplate": obrazac.datum_isplate,
            "oib_obveznika": obrazac.oib_obveznika,
            "naziv_obveznika": obrazac.naziv_obveznika,
            "broj_stavki": len(obrazac.stavke),
            "ukupno": {
                "bruto": obrazac.ukupno_bruto,
                "mio_1": obrazac.ukupno_mio_1,
                "mio_2": obrazac.ukupno_mio_2,
                "porez": obrazac.ukupno_porez,
                "prirez": obrazac.ukupno_prirez,
                "neto": obrazac.ukupno_neto,
                "zdravstveno": obrazac.ukupno_zdravstveno,
            },
            "requires_approval": True,
            "note": "JOPPD mora biti predan na ePorezna — predaja je na računovođi",
        }

    def get_stats(self) -> Dict[str, Any]:
        return {"joppd_generated": self._generation_count}
