"""
Nyx Light — ERP Export Engine

Generira strukturirane datoteke za uvoz u:
- CPP (Centar Poslovnog Planiranja) — XML format
- Synesis — CSV/JSON format

Svaki klijent može koristiti različiti ERP sustav.
Izvoz se generira TEK NAKON odobrenja knjiženja (Human-in-the-Loop).
"""

import csv
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.dom import minidom

logger = logging.getLogger("nyx_light.export")


class ERPExporter:
    """Generira izvozne datoteke za CPP i Synesis."""

    def __init__(self, export_dir: str = "data/exports"):
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self._export_count = 0
        logger.info("ERPExporter inicijaliziran → %s", self.export_dir)

    def export_cpp_xml(
        self,
        bookings: List[Dict[str, Any]],
        client_id: str,
        period: str = "",
    ) -> Dict[str, Any]:
        """
        Generiraj XML datoteku za uvoz u CPP.

        CPP XML format:
        <KnjizenjaImport>
          <Zaglavlje>
            <Klijent>...</Klijent>
            <Datum>...</Datum>
          </Zaglavlje>
          <Stavke>
            <Stavka>
              <RedniBroj>1</RedniBroj>
              <KontoDuguje>7200</KontoDuguje>
              <KontoPotrazuje>4000</KontoPotrazuje>
              <Iznos>1250.00</Iznos>
              <Opis>...</Opis>
              <DatumDokumenta>2026-02-26</DatumDokumenta>
              <OIB>12345678901</OIB>
            </Stavka>
          </Stavke>
        </KnjizenjaImport>
        """
        root = ET.Element("KnjizenjaImport")

        # Zaglavlje
        header = ET.SubElement(root, "Zaglavlje")
        ET.SubElement(header, "Klijent").text = client_id
        ET.SubElement(header, "Datum").text = datetime.now().strftime("%Y-%m-%d")
        ET.SubElement(header, "Period").text = period or datetime.now().strftime("%Y-%m")
        ET.SubElement(header, "BrojStavki").text = str(len(bookings))
        ET.SubElement(header, "Generator").text = "NyxLight-Racunovodja-v1.0"

        # Stavke
        stavke = ET.SubElement(root, "Stavke")
        for i, booking in enumerate(bookings, 1):
            stavka = ET.SubElement(stavke, "Stavka")
            ET.SubElement(stavka, "RedniBroj").text = str(i)
            ET.SubElement(stavka, "KontoDuguje").text = str(booking.get("konto_duguje", ""))
            ET.SubElement(stavka, "KontoPotrazuje").text = str(booking.get("konto_potrazuje", ""))
            ET.SubElement(stavka, "Iznos").text = f"{booking.get('iznos', 0):.2f}"
            ET.SubElement(stavka, "Valuta").text = booking.get("valuta", "EUR")
            ET.SubElement(stavka, "Opis").text = str(booking.get("opis", ""))
            ET.SubElement(stavka, "DatumDokumenta").text = str(
                booking.get("datum_dokumenta", datetime.now().strftime("%Y-%m-%d"))
            )
            ET.SubElement(stavka, "DatumKnjizenja").text = str(
                booking.get("datum_knjizenja", datetime.now().strftime("%Y-%m-%d"))
            )
            ET.SubElement(stavka, "OIB").text = str(booking.get("oib", ""))
            ET.SubElement(stavka, "PDVStopa").text = str(booking.get("pdv_stopa", "25"))
            ET.SubElement(stavka, "PDVIznos").text = f"{booking.get('pdv_iznos', 0):.2f}"

            if booking.get("poziv_na_broj"):
                ET.SubElement(stavka, "PozivNaBroj").text = str(booking["poziv_na_broj"])

        # Pretty print
        xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(
            indent="  ", encoding=None
        )

        # Save
        filename = f"cpp_{client_id}_{int(time.time())}.xml"
        filepath = self.export_dir / filename
        filepath.write_text(xml_str, encoding="utf-8")

        self._export_count += 1
        logger.info("CPP XML export: %s (%d stavki)", filename, len(bookings))

        return {
            "status": "exported",
            "erp": "CPP",
            "format": "XML",
            "file": str(filepath),
            "filename": filename,
            "records": len(bookings),
            "client_id": client_id,
        }

    def export_synesis_csv(
        self,
        bookings: List[Dict[str, Any]],
        client_id: str,
        delimiter: str = ";",
    ) -> Dict[str, Any]:
        """
        Generiraj CSV datoteku za uvoz u Synesis.

        Synesis CSV format (`;` delimiter):
        RedniBroj;KontoDuguje;KontoPotrazuje;Iznos;Opis;Datum;OIB;PDVStopa
        """
        filename = f"synesis_{client_id}_{int(time.time())}.csv"
        filepath = self.export_dir / filename

        fieldnames = [
            "RedniBroj", "KontoDuguje", "KontoPotrazuje", "Iznos",
            "Opis", "DatumDokumenta", "DatumKnjizenja", "OIB",
            "PDVStopa", "PDVIznos", "PozivNaBroj",
        ]

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()

            for i, booking in enumerate(bookings, 1):
                writer.writerow({
                    "RedniBroj": i,
                    "KontoDuguje": booking.get("konto_duguje", ""),
                    "KontoPotrazuje": booking.get("konto_potrazuje", ""),
                    "Iznos": f"{booking.get('iznos', 0):.2f}",
                    "Opis": booking.get("opis", ""),
                    "DatumDokumenta": booking.get("datum_dokumenta", ""),
                    "DatumKnjizenja": booking.get("datum_knjizenja", ""),
                    "OIB": booking.get("oib", ""),
                    "PDVStopa": booking.get("pdv_stopa", "25"),
                    "PDVIznos": f"{booking.get('pdv_iznos', 0):.2f}",
                    "PozivNaBroj": booking.get("poziv_na_broj", ""),
                })

        self._export_count += 1
        logger.info("Synesis CSV export: %s (%d stavki)", filename, len(bookings))

        return {
            "status": "exported",
            "erp": "Synesis",
            "format": "CSV",
            "file": str(filepath),
            "filename": filename,
            "records": len(bookings),
            "client_id": client_id,
        }

    def export_synesis_json(
        self,
        bookings: List[Dict[str, Any]],
        client_id: str,
    ) -> Dict[str, Any]:
        """Generiraj JSON datoteku za Synesis API import."""
        payload = {
            "meta": {
                "client_id": client_id,
                "export_date": datetime.now().isoformat(),
                "generator": "NyxLight-Racunovodja-v1.0",
                "record_count": len(bookings),
            },
            "bookings": [
                {
                    "redni_broj": i,
                    "konto_duguje": b.get("konto_duguje", ""),
                    "konto_potrazuje": b.get("konto_potrazuje", ""),
                    "iznos": round(b.get("iznos", 0), 2),
                    "opis": b.get("opis", ""),
                    "datum_dokumenta": b.get("datum_dokumenta", ""),
                    "datum_knjizenja": b.get("datum_knjizenja", ""),
                    "oib": b.get("oib", ""),
                    "pdv_stopa": b.get("pdv_stopa", 25),
                    "pdv_iznos": round(b.get("pdv_iznos", 0), 2),
                }
                for i, b in enumerate(bookings, 1)
            ],
        }

        filename = f"synesis_{client_id}_{int(time.time())}.json"
        filepath = self.export_dir / filename
        filepath.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

        self._export_count += 1
        return {
            "status": "exported",
            "erp": "Synesis",
            "format": "JSON",
            "file": str(filepath),
            "filename": filename,
            "records": len(bookings),
        }

    def export(
        self,
        bookings: List[Dict[str, Any]],
        client_id: str,
        erp: str = "CPP",
        fmt: str = "XML",
    ) -> Dict[str, Any]:
        """Univerzalni export — automatski odabir formata."""
        erp_upper = erp.upper()

        if erp_upper == "CPP":
            return self.export_cpp_xml(bookings, client_id)
        elif erp_upper == "SYNESIS" and fmt.upper() == "CSV":
            return self.export_synesis_csv(bookings, client_id)
        elif erp_upper == "SYNESIS":
            return self.export_synesis_json(bookings, client_id)
        else:
            return {"status": "error", "message": f"Nepodržani ERP: {erp}"}

    def get_stats(self) -> Dict[str, Any]:
        exports = list(self.export_dir.glob("*"))
        return {
            "total_exports": self._export_count,
            "files_on_disk": len(exports),
            "export_dir": str(self.export_dir),
        }
