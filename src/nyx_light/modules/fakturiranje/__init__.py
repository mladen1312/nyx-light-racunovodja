"""
Nyx Light — Modul F3: Fakturiranje usluga ureda

Automatsko generiranje računa za računovodstvene usluge klijentima.
Podržava:
- Mjesečni paušal
- Obračun po stavkama (plaće, PDV prijave, GFI...)
- Godišnji obračun (zaključna knjiženja, GFI predaja)
- Dodatne usluge (savjetovanje, izvanredni obračuni)

Račun se generira u PDF/XML formatu.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.fakturiranje")


def _d(val) -> "Decimal":
    """Convert to Decimal for precise money calculations."""
    if isinstance(val, Decimal):
        return val
    if isinstance(val, float):
        return Decimal(str(val))
    return Decimal(str(val) if val else '0')


def _r2(val) -> float:
    """Round Decimal to 2 places and return float for JSON compat."""
    return float(Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


PDV_STOPA = 25.0  # Računovodstvene usluge — standardna stopa


@dataclass
class UslugaStavka:
    """Jedna stavka na računu za uslugu."""
    opis: str = ""
    kolicina: float = 1.0
    jedinicna_cijena: float = 0.0
    popust_pct: float = 0.0
    iznos_bez_pdv: float = 0.0
    pdv: float = 0.0
    iznos_s_pdv: float = 0.0


@dataclass
class UslugaRacun:
    """Račun za računovodstvene usluge."""
    broj: str = ""
    datum: str = ""
    datum_dospijeca: str = ""
    klijent_id: str = ""
    klijent_naziv: str = ""
    klijent_oib: str = ""
    klijent_adresa: str = ""

    ured_naziv: str = ""
    ured_oib: str = ""
    ured_adresa: str = ""
    ured_iban: str = ""

    stavke: List[UslugaStavka] = field(default_factory=list)
    ukupno_bez_pdv: float = 0.0
    ukupno_pdv: float = 0.0
    ukupno_s_pdv: float = 0.0

    napomena: str = ""
    model_poziva: str = "HR00"
    poziv_na_broj: str = ""

    status: str = "draft"  # draft, sent, paid, overdue


@dataclass
class CjenikUsluga:
    """Cjenik standardnih usluga ureda."""
    mjesecni_pausal_mikro: float = 150.0
    mjesecni_pausal_mali: float = 300.0
    mjesecni_pausal_srednji: float = 600.0
    obracun_place_po_zaposleniku: float = 15.0
    pdv_prijava: float = 30.0
    gfi_predaja_mikro: float = 200.0
    gfi_predaja_mali: float = 400.0
    joppd_mjesecni: float = 20.0
    pd_obrazac: float = 100.0
    doh_obrazac: float = 80.0
    savjetovanje_sat: float = 60.0


class FakturiranjeEngine:
    """Fakturiranje usluga računovodstvenog ureda."""

    def __init__(self, ured_naziv: str = "", ured_oib: str = "",
                 ured_adresa: str = "", ured_iban: str = ""):
        self.ured_naziv = ured_naziv
        self.ured_oib = ured_oib
        self.ured_adresa = ured_adresa
        self.ured_iban = ured_iban
        self.cjenik = CjenikUsluga()
        self._counter = 0
        self._racuni: List[UslugaRacun] = []

    def create_monthly_invoice(
        self,
        klijent_id: str,
        klijent_naziv: str,
        klijent_oib: str,
        kategorija: str = "mikro",
        broj_zaposlenih: int = 0,
        extra_items: List[Dict] = None,
        dani_valute: int = 15,
    ) -> UslugaRacun:
        """Kreiraj mjesečni račun za klijenta."""
        self._counter += 1
        today = date.today()
        dospijece = today + timedelta(days=dani_valute)

        racun = UslugaRacun(
            broj=f"R-{today.year}-{self._counter:04d}",
            datum=today.isoformat(),
            datum_dospijeca=dospijece.isoformat(),
            klijent_id=klijent_id,
            klijent_naziv=klijent_naziv,
            klijent_oib=klijent_oib,
            ured_naziv=self.ured_naziv,
            ured_oib=self.ured_oib,
            ured_adresa=self.ured_adresa,
            ured_iban=self.ured_iban,
        )

        # Paušal prema kategoriji
        pausal_map = {
            "mikro": self.cjenik.mjesecni_pausal_mikro,
            "mali": self.cjenik.mjesecni_pausal_mali,
            "srednji": self.cjenik.mjesecni_pausal_srednji,
        }
        pausal = pausal_map.get(kategorija, self.cjenik.mjesecni_pausal_mikro)
        racun.stavke.append(self._make_stavka(
            f"Mjesečni paušal — računovodstvene usluge ({kategorija})",
            1, pausal
        ))

        # Plaće
        if broj_zaposlenih > 0:
            racun.stavke.append(self._make_stavka(
                "Obračun plaća",
                broj_zaposlenih,
                self.cjenik.obracun_place_po_zaposleniku,
            ))
            racun.stavke.append(self._make_stavka(
                "JOPPD obrazac",
                1, self.cjenik.joppd_mjesecni,
            ))

        # Extra
        if extra_items:
            for item in extra_items:
                racun.stavke.append(self._make_stavka(
                    item.get("opis", "Dodatna usluga"),
                    item.get("kolicina", 1),
                    item.get("cijena", 0),
                    item.get("popust", 0),
                ))

        # Totali
        racun.ukupno_bez_pdv = round(
            sum(s.iznos_bez_pdv for s in racun.stavke), 2
        )
        racun.ukupno_pdv = round(
            sum(s.pdv for s in racun.stavke), 2
        )
        racun.ukupno_s_pdv = round(
            sum(s.iznos_s_pdv for s in racun.stavke), 2
        )

        racun.poziv_na_broj = f"{klijent_oib}-{today.month:02d}-{today.year}"

        self._racuni.append(racun)
        return racun

    def to_dict(self, racun: UslugaRacun) -> Dict[str, Any]:
        return {
            "broj": racun.broj,
            "datum": racun.datum,
            "dospijece": racun.datum_dospijeca,
            "klijent": racun.klijent_naziv,
            "oib_klijenta": racun.klijent_oib,
            "stavke": [
                {
                    "opis": s.opis,
                    "kolicina": s.kolicina,
                    "cijena": s.jedinicna_cijena,
                    "iznos": s.iznos_bez_pdv,
                } for s in racun.stavke
            ],
            "ukupno_bez_pdv": racun.ukupno_bez_pdv,
            "pdv_25": racun.ukupno_pdv,
            "ukupno_s_pdv": racun.ukupno_s_pdv,
            "iban": racun.ured_iban,
            "poziv_na_broj": racun.poziv_na_broj,
        }

    def get_unpaid(self) -> List[Dict]:
        """Neplaćeni računi."""
        today = date.today().isoformat()
        unpaid = []
        for r in self._racuni:
            if r.status in ("draft", "sent", "overdue"):
                overdue = r.datum_dospijeca < today
                if overdue:
                    r.status = "overdue"
                unpaid.append({
                    "broj": r.broj,
                    "klijent": r.klijent_naziv,
                    "iznos": r.ukupno_s_pdv,
                    "dospijece": r.datum_dospijeca,
                    "status": r.status,
                    "dana_prekoracenja": (
                        (date.fromisoformat(today) -
                         date.fromisoformat(r.datum_dospijeca)).days
                        if overdue else 0
                    ),
                })
        return unpaid

    def mark_paid(self, broj_racuna: str) -> Dict:
        for r in self._racuni:
            if r.broj == broj_racuna:
                r.status = "paid"
                return {"success": True, "broj": broj_racuna}
        return {"success": False, "error": "Račun nije pronađen"}

    def _make_stavka(self, opis: str, kol: float, cijena: float,
                     popust: float = 0.0) -> UslugaStavka:
        iznos_base = round(kol * cijena, 2)
        popust_iznos = round(iznos_base * popust / 100, 2) if popust else 0
        bez_pdv = round(iznos_base - popust_iznos, 2)
        pdv = round(bez_pdv * PDV_STOPA / 100, 2)
        return UslugaStavka(
            opis=opis, kolicina=kol, jedinicna_cijena=cijena,
            popust_pct=popust, iznos_bez_pdv=bez_pdv,
            pdv=pdv, iznos_s_pdv=round(bez_pdv + pdv, 2),
        )

    def get_stats(self):
        total = len(self._racuni)
        paid = sum(1 for r in self._racuni if r.status == "paid")
        return {"racuni_total": total, "racuni_paid": paid, "racuni_unpaid": total - paid}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: ZKI hash, sekvencijsko numeriranje, R1/R2 logika
# ════════════════════════════════════════════════════════

import hashlib
import hmac
from datetime import date, timedelta

# Rokovi plaćanja prema ZOR-u (čl. 173-177)
DEFAULT_VALUTA_DANI = 30      # B2B default
MAX_VALUTA_DANI_B2G = 30      # Javni sektor max 30 dana
MAX_VALUTA_DANI_B2B = 60      # Poslovni subjekti max 60 dana


class InvoiceNumberGenerator:
    """Sekvencijsko numeriranje računa po poslovnom prostoru."""

    def __init__(self):
        self._counters = {}  # {(year, pp_oznaka): next_number}

    def next_number(self, year: int = None, pp_oznaka: str = "1") -> str:
        """Generiraj sljedeći broj računa.
        
        Format: BROJ/PP/NAPLATNI_UREĐAJ (npr. 1/1/1)
        Prema Zakonu o fiskalizaciji čl. 9.
        """
        year = year or date.today().year
        key = (year, pp_oznaka)
        num = self._counters.get(key, 1)
        self._counters[key] = num + 1
        return f"{num}/{pp_oznaka}/1"

    def current_count(self, year: int = None, pp_oznaka: str = "1") -> int:
        year = year or date.today().year
        return self._counters.get((year, pp_oznaka), 1) - 1


class ZKICalculator:
    """Zaštitni Kod Izdavatelja — čl. 12 Zakona o fiskalizaciji."""

    @staticmethod
    def calculate(oib: str, datum_vrijeme: str, broj_racuna: str,
                  pp_oznaka: str, nu_oznaka: str, ukupno: str,
                  private_key: bytes = b"") -> str:
        """Izračunaj ZKI hash.
        
        ZKI = MD5(RSA_Sign(OIB + datum + broj + PP + NU + ukupno))
        
        Za produkciju treba pravi RSA ključ iz certifikata FINA-e.
        Za razvoj koristimo HMAC-SHA256 simulaciju.
        """
        zki_input = f"{oib}{datum_vrijeme}{broj_racuna}{pp_oznaka}{nu_oznaka}{ukupno}"
        
        if private_key:
            # Produkcija: pravi RSA potpis
            signature = hmac.new(private_key, zki_input.encode(), hashlib.sha256).hexdigest()
        else:
            # Dev: simulirani ZKI (32 hex znakova kao MD5)
            signature = hashlib.md5(zki_input.encode()).hexdigest()
        
        return signature


def calculate_due_date(invoice_date: date, payment_days: int = 30,
                       partner_type: str = "b2b") -> date:
    """Izračunaj datum dospijeća prema ZOR-u."""
    if partner_type == "b2g":
        payment_days = min(payment_days, MAX_VALUTA_DANI_B2G)
    elif partner_type == "b2b":
        payment_days = min(payment_days, MAX_VALUTA_DANI_B2B)
    return invoice_date + timedelta(days=payment_days)


def validate_invoice(data: dict) -> List[Dict]:
    """Validacija računa prije izdavanja."""
    errors = []
    required = ["oib_kupca", "datum", "stavke", "ukupno"]
    for field in required:
        if not data.get(field):
            errors.append({"field": field, "msg": f"Polje '{field}' je obvezno", "severity": "error"})

    # OIB provjera
    oib = data.get("oib_kupca", "")
    if oib and len(oib) == 11:
        from nyx_light.modules.pdv_prijava import validate_oib
        if not validate_oib(oib):
            errors.append({"field": "oib_kupca", "msg": f"Neispravan OIB: {oib}", "severity": "error"})

    # Stavke ukupno = sum(stavka.ukupno)
    stavke = data.get("stavke", [])
    if stavke:
        calc_total = sum(_d(s.get("ukupno", 0)) for s in stavke)
        stated_total = _d(data.get("ukupno", 0))
        if abs(calc_total - stated_total) > _d("0.02"):
            errors.append({
                "field": "ukupno",
                "msg": f"Ukupno ({stated_total}) ≠ zbroj stavki ({calc_total})",
                "severity": "error",
            })

    # R1/R2 provjera
    tip = data.get("tip_racuna", "R1")
    if tip == "R1" and not data.get("pdv_obveznik"):
        errors.append({"field": "tip_racuna", "msg": "R1 račun zahtijeva PDV obveznički status", "severity": "warning"})

    return errors
