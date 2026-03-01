"""
Nyx Light — Modul A2: Validacija izlaznih računa

Provjerava formalne elemente prema čl. 63. Zakona o PDV-u:
- OIB izdavatelja i primatelja
- Naziv, adresa, datum, redni broj
- Opis isporuke/usluge
- PDV stopa i iznos
- Ukupni iznos

Za EU transakcije: provjera reverse charge uvjeta.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.outgoing_invoice")


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


# PDV stope RH
PDV_STOPE_RH = {25.0, 13.0, 5.0, 0.0}


@dataclass
class InvoiceValidationResult:
    """Rezultat validacije izlaznog računa."""
    valid: bool = True
    errors: List[str] = field(default_factory=list)       # Greške koje sprječavaju validnost
    warnings: List[str] = field(default_factory=list)      # Upozorenja (ne sprječavaju)
    suggestions: List[str] = field(default_factory=list)   # Prijedlozi poboljšanja
    pdv_status: str = ""                                   # "standard", "reverse_charge", "exempt"
    requires_review: bool = False


class OutgoingInvoiceValidator:
    """
    Validacija izlaznih računa prema Zakonu o PDV-u.
    
    AI provjerava formalne elemente — sadržajnu provjeru 
    (je li usluga izvršena, je li cijena ispravna) radi računovođa.
    """

    def __init__(self):
        self._validation_count = 0

    def validate(self, invoice: Dict[str, Any]) -> InvoiceValidationResult:
        """Validiraj izlazni račun."""
        result = InvoiceValidationResult()

        # ── 1. Obvezni elementi (čl. 63. Zakona o PDV-u) ──
        
        # Broj računa
        if not invoice.get("broj_racuna"):
            result.errors.append("Nedostaje broj računa (čl. 63. st. 1. t. 1.)")
            result.valid = False

        # Datum izdavanja
        if not invoice.get("datum_izdavanja"):
            result.errors.append("Nedostaje datum izdavanja (čl. 63. st. 1. t. 2.)")
            result.valid = False

        # OIB izdavatelja
        oib_izdavatelja = invoice.get("oib_izdavatelja", "")
        if not self._valid_oib(oib_izdavatelja):
            result.errors.append("Neispravan OIB izdavatelja (čl. 63. st. 1. t. 3.)")
            result.valid = False

        # Naziv i adresa izdavatelja
        if not invoice.get("naziv_izdavatelja"):
            result.errors.append("Nedostaje naziv izdavatelja")
            result.valid = False
        if not invoice.get("adresa_izdavatelja"):
            result.warnings.append("Nedostaje adresa izdavatelja")

        # OIB primatelja
        oib_primatelja = invoice.get("oib_primatelja", "")
        if not oib_primatelja:
            result.warnings.append(
                "Nedostaje OIB primatelja — obvezan za B2B transakcije (čl. 63. st. 1. t. 4.)"
            )
            result.requires_review = True
        elif not self._valid_oib(oib_primatelja):
            result.errors.append("Neispravan OIB primatelja")
            result.valid = False

        # Opis isporuke/usluge
        if not invoice.get("opis_isporuke"):
            result.errors.append("Nedostaje opis isporuke dobara ili usluge (čl. 63. st. 1. t. 5.)")
            result.valid = False

        # ── 2. Financijski elementi ──

        iznos = invoice.get("iznos", 0)
        pdv_stopa = invoice.get("pdv_stopa")
        pdv_iznos = invoice.get("pdv_iznos", 0)

        if iznos <= 0:
            result.errors.append("Iznos mora biti pozitivan")
            result.valid = False

        if pdv_stopa is not None:
            if pdv_stopa not in PDV_STOPE_RH:
                result.warnings.append(
                    f"Nestandarna PDV stopa: {pdv_stopa}% — "
                    f"standardne stope u RH: 25%, 13%, 5%, 0%"
                )
                result.requires_review = True

            # Provjera matematičke ispravnosti PDV-a
            if pdv_stopa > 0 and iznos > 0:
                expected_pdv = round(iznos * pdv_stopa / (100 + pdv_stopa), 2)
                if pdv_iznos and abs(pdv_iznos - expected_pdv) > 0.02:
                    result.warnings.append(
                        f"PDV iznos ({pdv_iznos:.2f}) ne odgovara stopi {pdv_stopa}% "
                        f"na iznos {iznos:.2f} — očekivano: {expected_pdv:.2f}"
                    )
        else:
            result.errors.append("Nedostaje PDV stopa (čl. 63. st. 1. t. 7.)")
            result.valid = False

        # ── 3. EU transakcije ──
        
        zemlja_primatelja = invoice.get("zemlja_primatelja", "HR")
        eu_vat_id = invoice.get("eu_vat_id", "")

        if zemlja_primatelja != "HR" and zemlja_primatelja:
            result.pdv_status = self._check_eu_transaction(
                zemlja_primatelja, eu_vat_id, pdv_stopa, result
            )
        else:
            result.pdv_status = "standard"

        # ── 4. Specifične provjere ──

        # Valuta
        valuta = invoice.get("valuta", "EUR")
        if valuta != "EUR":
            result.warnings.append(
                f"Račun u stranoj valuti ({valuta}) — "
                "potreban preračun u EUR po tečaju HNB na dan nastanka obveze"
            )

        # Rok plaćanja
        if not invoice.get("rok_placanja"):
            result.suggestions.append("Preporučeno navesti rok plaćanja")

        # Fiskalizacija
        if invoice.get("gotovinski", False):
            if not invoice.get("jir"):
                result.errors.append(
                    "Gotovinski račun bez JIR broja — "
                    "obveza fiskalizacije (Zakon o fiskalizaciji čl. 16.)"
                )
                result.valid = False

        self._validation_count += 1
        return result

    def _check_eu_transaction(
        self, zemlja: str, eu_vat_id: str, pdv_stopa: float,
        result: InvoiceValidationResult,
    ) -> str:
        """Provjeri EU transakciju."""
        eu_countries = {
            "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
            "FR", "GR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
            "PL", "PT", "RO", "SE", "SI", "SK",
        }

        if zemlja.upper() in eu_countries:
            if eu_vat_id:
                # Reverse charge — PDV mora biti 0
                if pdv_stopa and pdv_stopa > 0:
                    result.warnings.append(
                        f"EU kupac s VAT ID-om ({eu_vat_id}) — "
                        "primjenjuje se reverse charge, PDV stopa treba biti 0% "
                        "(čl. 41. st. 1. Zakona o PDV-u)"
                    )
                    result.requires_review = True

                result.suggestions.append(
                    f"Provjeri valjanost VAT ID-a: {eu_vat_id} na VIES sustavu"
                )
                result.suggestions.append(
                    "Unijeti u zbirnu prijavu (EC Sales List)"
                )
                return "reverse_charge"
            else:
                result.warnings.append(
                    f"EU transakcija ({zemlja}) bez VAT ID-a primatelja — "
                    "primjenjuje se domaća PDV stopa (nije reverse charge)"
                )
                return "standard"
        else:
            # Treća zemlja (izvan EU)
            result.suggestions.append(
                f"Izvoz u treću zemlju ({zemlja}) — "
                "PDV oslobođenje uz dokaz o izvozu (čl. 45. Zakona o PDV-u)"
            )
            return "export"

    def _valid_oib(self, oib: str) -> bool:
        """Provjeri OIB format (11 znamenki + kontrolna)."""
        if not oib or not re.match(r'^\d{11}$', oib):
            return False

        # Kontrolna znamenka (ISO 7064, MOD 11,10)
        a = 10
        for digit in oib[:10]:
            a = (a + int(digit)) % 10
            if a == 0:
                a = 10
            a = (a * 2) % 11
        kontrolna = (11 - a) % 10
        return kontrolna == int(oib[10])

    def get_stats(self) -> Dict[str, Any]:
        return {"validations": self._validation_count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: R1/R2 logika, rabat, PDV obračun po stavci, cashflow prognoza
# ════════════════════════════════════════════════════════

from datetime import date, timedelta


PDV_STOPE = {25.0: "25%", 13.0: "13%", 5.0: "5%", 0.0: "0%"}


class IzlazniRacunCalculator:
    """Kalkulacija izlaznog računa s PDV-om, rabatom i fiskalizacijom."""

    def __init__(self):
        self._count = 0

    def calculate_stavke(self, stavke: list) -> dict:
        """Izračunaj sve stavke računa s rabatom i PDV-om."""
        result_stavke = []
        ukupno_osnovica = _d(0)
        ukupno_pdv = _d(0)
        ukupno_rabat = _d(0)
        pdv_rekapitulacija = {}

        for i, s in enumerate(stavke, 1):
            kolicina = _d(s.get("kolicina", 1))
            cijena = _d(s.get("cijena", 0))
            rabat_pct = _d(s.get("rabat_pct", 0))
            pdv_stopa = _d(s.get("pdv_stopa", 25))

            bruto_stavka = _r2(kolicina * cijena)
            rabat_iznos = _r2(_d(bruto_stavka) * rabat_pct / _d(100))
            osnovica = _r2(_d(bruto_stavka) - _d(rabat_iznos))
            pdv = _r2(_d(osnovica) * pdv_stopa / _d(100))
            ukupno_stavka = _r2(_d(osnovica) + _d(pdv))

            ukupno_osnovica += _d(osnovica)
            ukupno_pdv += _d(pdv)
            ukupno_rabat += _d(rabat_iznos)

            # PDV rekapitulacija po stopama
            stopa_key = float(pdv_stopa)
            if stopa_key not in pdv_rekapitulacija:
                pdv_rekapitulacija[stopa_key] = {"osnovica": _d(0), "pdv": _d(0)}
            pdv_rekapitulacija[stopa_key]["osnovica"] += _d(osnovica)
            pdv_rekapitulacija[stopa_key]["pdv"] += _d(pdv)

            result_stavke.append({
                "rb": i,
                "opis": s.get("opis", ""),
                "kolicina": float(kolicina),
                "jmj": s.get("jmj", "kom"),
                "cijena": float(cijena),
                "rabat_pct": float(rabat_pct),
                "rabat_iznos": rabat_iznos,
                "osnovica": osnovica,
                "pdv_stopa": float(pdv_stopa),
                "pdv": pdv,
                "ukupno": ukupno_stavka,
            })

        rekapitulacija = {
            f"{stopa}%": {"osnovica": _r2(v["osnovica"]), "pdv": _r2(v["pdv"])}
            for stopa, v in sorted(pdv_rekapitulacija.items())
        }

        self._count += 1
        return {
            "stavke": result_stavke,
            "ukupno_osnovica": _r2(ukupno_osnovica),
            "ukupno_pdv": _r2(ukupno_pdv),
            "ukupno_rabat": _r2(ukupno_rabat),
            "sveukupno": _r2(ukupno_osnovica + ukupno_pdv),
            "pdv_rekapitulacija": rekapitulacija,
            "valuta": "EUR",
        }

    def cashflow_projection(self, invoices: list) -> dict:
        """Prognoza priljeva po tjednima na temelju izdanih računa."""
        today = date.today()
        weeks = {f"week_{i}": _d(0) for i in range(1, 9)}

        for inv in invoices:
            try:
                due = date.fromisoformat(inv.get("datum_dospijeca", ""))
                diff = (due - today).days
                week_num = max(1, min(8, (diff // 7) + 1))
                weeks[f"week_{week_num}"] += _d(inv.get("iznos", 0))
            except (ValueError, TypeError):
                weeks["week_8"] += _d(inv.get("iznos", 0))

        return {k: _r2(v) for k, v in weeks.items()}

    def get_stats(self):
        return {"invoices_calculated": self._count}
