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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Godišnji odmor, otpremnina, evidencija radnog vremena
# ════════════════════════════════════════════════════════

from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta

def _d(val) -> Decimal:
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val) -> float:
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Zakon o radu — godišnji odmor (čl. 77-85)
MIN_GODISNJI_ODMOR = 20  # Radnih dana (4 tjedna)
MAX_GODISNJI_ODMOR = 30  # Radnih dana (6 tjedana)

# Otpremnina (čl. 126 ZOR)
OTPREMNINA_MIN_STAZ = 2  # Minimalno 2 godine za pravo na otpremninu
OTPREMNINA_PO_GODINI = 1/3  # 1/3 prosječne plaće po godini staža
MAX_OTPREMNINA_MJESECI = 6  # Max 6 prosječnih plaća


class GodisnjiOdmorCalculator:
    """Izračun prava na godišnji odmor prema ZOR-u."""

    @staticmethod
    def calculate(
        staz_godina: int,
        djeca_count: int = 0,
        invaliditet: bool = False,
        rad_u_smjenama: bool = False,
        kolektivni_bonus: int = 0,
    ) -> dict:
        """Izračunaj dane godišnjeg odmora."""
        dani = MIN_GODISNJI_ODMOR  # Zakonski minimum 20

        # Stažni bonus (1 dan na 5 godina staža, uobičajeno KU)
        dani += staz_godina // 5

        # Djeca bonus (1 dan po djetetu, uobičajeno KU)
        dani += djeca_count

        # Invaliditet (+3 dana)
        if invaliditet:
            dani += 3

        # Smjenski rad (+2 dana)
        if rad_u_smjenama:
            dani += 2

        # Kolektivni ugovor bonus
        dani += kolektivni_bonus

        dani = min(dani, MAX_GODISNJI_ODMOR)

        return {
            "dani_godisnjeg": dani,
            "zakonski_minimum": MIN_GODISNJI_ODMOR,
            "zakonski_maksimum": MAX_GODISNJI_ODMOR,
            "detalji": {
                "bazni": MIN_GODISNJI_ODMOR,
                "staz_bonus": staz_godina // 5,
                "djeca_bonus": djeca_count,
                "invaliditet_bonus": 3 if invaliditet else 0,
                "smjenski_bonus": 2 if rad_u_smjenama else 0,
                "kolektivni_bonus": kolektivni_bonus,
            },
            "zakonski_temelj": "Zakon o radu, čl. 77-85",
        }


class OtpremninaCalculator:
    """Izračun otpremnine pri otkazu od strane poslodavca."""

    @staticmethod
    def calculate(
        prosjecna_placa_3mj: float,
        staz_kod_poslodavca_godina: int,
        razlog: str = "poslovno_uvjetovani",
    ) -> dict:
        """Izračunaj otpremninu prema ZOR-u čl. 126."""
        if staz_kod_poslodavca_godina < OTPREMNINA_MIN_STAZ:
            return {
                "pravo_na_otpremninu": False,
                "razlog": f"Staž {staz_kod_poslodavca_godina} god < {OTPREMNINA_MIN_STAZ} god minimum",
            }

        placa = _d(prosjecna_placa_3mj)
        po_godini = _r2(placa * _d(OTPREMNINA_PO_GODINI))
        otpremnina = _r2(_d(po_godini) * _d(staz_kod_poslodavca_godina))
        max_iznos = _r2(placa * _d(MAX_OTPREMNINA_MJESECI))
        otpremnina = min(otpremnina, max_iznos)

        # Neoporezivi dio otpremnine (do 6.500 EUR za 2026.)
        NEOPOREZIVI_DIO = 6500.0
        oporezivi = _r2(max(0, _d(otpremnina) - _d(NEOPOREZIVI_DIO)))

        return {
            "pravo_na_otpremninu": True,
            "prosjecna_placa_3mj": _r2(placa),
            "staz_kod_poslodavca": staz_kod_poslodavca_godina,
            "po_godini_staza": po_godini,
            "otpremnina_bruto": otpremnina,
            "neoporezivi_dio": min(otpremnina, NEOPOREZIVI_DIO),
            "oporezivi_dio": oporezivi,
            "max_zakonski": max_iznos,
            "razlog_otkaza": razlog,
            "zakonski_temelj": "Zakon o radu, čl. 126",
            "napomena": "Neoporezivo do 6.500 EUR (čl. 7 st. 2 t. 27 Pravilnika)",
        }


class RadnoVrijemeValidator:
    """Provjera evidencije radnog vremena prema ZOR-u."""

    MAX_TJEDNO = 40       # Puno radno vrijeme
    MAX_PREKOVREMENO_TJEDNO = 50  # S prekovremenim max 50h
    MAX_PREKOVREMENO_GODISNJE = 180  # Max 180h godišnje
    MIN_DNEVNI_ODMOR = 12  # Sati
    MIN_TJEDNI_ODMOR = 24  # Sati (+ 12h dnevnog = 36h)

    @staticmethod
    def validate_tjedan(sati_po_danu: list) -> dict:
        """Validiraj tjednu evidenciju radnog vremena."""
        errors = []
        ukupno = sum(sati_po_danu)

        if ukupno > 50:
            errors.append(f"Tjedno {ukupno}h > 50h (ZOR čl. 65)")
        if any(s > 12 for s in sati_po_danu):
            errors.append("Smjena > 12h — ugrožen dnevni odmor od 12h (ZOR čl. 74)")
        prekovremeno = max(0, ukupno - 40)

        return {
            "ukupno_sati": ukupno,
            "redovno": min(ukupno, 40),
            "prekovremeno": prekovremeno,
            "errors": errors,
            "valid": len(errors) == 0,
        }


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Godišnji odmor, staž, prijava/odjava HZMO/HZZO
# ════════════════════════════════════════════════════════

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP


def _d(val):
    if isinstance(val, Decimal): return val
    return Decimal(str(val) if val else '0')

def _r2(val):
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# Minimalni godišnji odmor prema Zakonu o radu čl. 77
MIN_GODISNJI_ODMOR_DANA = 20  # radnih dana (4 tjedna)

# Uvećanje godišnjeg odmora (tipični kolektivni ugovor)
UVECANJA_GO = {
    "staz_5_10": 1,      # +1 dan za 5-10 god staža
    "staz_10_20": 2,     # +2 dana za 10-20
    "staz_20_plus": 3,   # +3 dana za 20+
    "djeca_do_7": 2,     # +2 dana po djetetu do 7 god
    "djeca_7_15": 1,     # +1 dan po djetetu 7-15 god
    "invalidnost": 3,    # +3 dana invalidnost
    "samohrani": 2,      # +2 dana samohrani roditelj
}


class GodisnjiOdmorCalculator:
    """Izračun godišnjeg odmora prema Zakonu o radu."""

    @staticmethod
    def calculate(
        staz_godina: int,
        djeca_do_7: int = 0,
        djeca_7_15: int = 0,
        invalidnost: bool = False,
        samohrani: bool = False,
        datum_zaposlenja: str = "",
        proporcionalno: bool = False,
    ) -> dict:
        """Izračunaj ukupni godišnji odmor u radnim danima."""
        dani = MIN_GODISNJI_ODMOR_DANA
        detalji = [f"Osnovni: {MIN_GODISNJI_ODMOR_DANA} dana"]

        # Staž
        if staz_godina >= 20:
            dani += UVECANJA_GO["staz_20_plus"]
            detalji.append(f"Staž 20+: +{UVECANJA_GO['staz_20_plus']}")
        elif staz_godina >= 10:
            dani += UVECANJA_GO["staz_10_20"]
            detalji.append(f"Staž 10-20: +{UVECANJA_GO['staz_10_20']}")
        elif staz_godina >= 5:
            dani += UVECANJA_GO["staz_5_10"]
            detalji.append(f"Staž 5-10: +{UVECANJA_GO['staz_5_10']}")

        # Djeca
        if djeca_do_7 > 0:
            bonus = djeca_do_7 * UVECANJA_GO["djeca_do_7"]
            dani += bonus
            detalji.append(f"Djeca <7g ({djeca_do_7}): +{bonus}")
        if djeca_7_15 > 0:
            bonus = djeca_7_15 * UVECANJA_GO["djeca_7_15"]
            dani += bonus
            detalji.append(f"Djeca 7-15g ({djeca_7_15}): +{bonus}")

        if invalidnost:
            dani += UVECANJA_GO["invalidnost"]
            detalji.append(f"Invalidnost: +{UVECANJA_GO['invalidnost']}")
        if samohrani:
            dani += UVECANJA_GO["samohrani"]
            detalji.append(f"Samohrani roditelj: +{UVECANJA_GO['samohrani']}")

        # Proporcionalno za nepunu godinu
        prop_dani = dani
        if proporcionalno and datum_zaposlenja:
            try:
                zap = date.fromisoformat(datum_zaposlenja)
                today = date.today()
                kraj_godine = date(today.year, 12, 31)
                mjeseci_rada = min(12, max(1, (kraj_godine.month - zap.month + 1)
                                  if zap.year == today.year else 12))
                prop_dani = int(dani * mjeseci_rada / 12)
                detalji.append(f"Proporcionalno ({mjeseci_rada}/12 mj): {prop_dani} dana")
            except ValueError:
                pass

        return {
            "ukupno_dana": prop_dani if proporcionalno else dani,
            "puni_odmor_dana": dani,
            "detalji": detalji,
            "zakonski_minimum": MIN_GODISNJI_ODMOR_DANA,
            "zakonski_temelj": "Zakon o radu čl. 77-85",
        }


class HZMOPrijava:
    """Generiranje podataka za prijavu/odjavu na HZMO/HZZO."""

    @staticmethod
    def prijava_radnika(data: dict) -> dict:
        """Generiraj strukturu za M-1P obrazac (prijava na HZMO)."""
        return {
            "obrazac": "M-1P",
            "tip": "prijava",
            "oib_radnika": data.get("oib", ""),
            "ime_prezime": data.get("ime_prezime", ""),
            "datum_pocetka": data.get("datum_pocetka", ""),
            "radno_vrijeme": data.get("radno_vrijeme", "puno"),
            "sati_tjedno": data.get("sati_tjedno", 40),
            "vrsta_ugovora": data.get("vrsta_ugovora", "neodredjeno"),
            "sifra_strucne_spreme": data.get("ss_sifra", ""),
            "staz_osiguranja_prijenos": data.get("staz_mjeseci", 0),
            "platform": "eHZMO",
            "rok_prijave": "8 dana od dana početka rada",
            "requires_approval": True,
        }

    @staticmethod
    def odjava_radnika(data: dict) -> dict:
        """Generiraj strukturu za M-2P obrazac (odjava s HZMO)."""
        return {
            "obrazac": "M-2P",
            "tip": "odjava",
            "oib_radnika": data.get("oib", ""),
            "ime_prezime": data.get("ime_prezime", ""),
            "datum_prestanka": data.get("datum_prestanka", ""),
            "razlog_prestanka": data.get("razlog", "sporazumni"),
            "otkazni_rok_dana": data.get("otkazni_rok", 0),
            "platform": "eHZMO",
            "rok_odjave": "8 dana od prestanka rada",
            "requires_approval": True,
        }
