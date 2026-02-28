"""
Nyx Light — Modul A5: Blagajna (Gotovinski promet)

Funkcionalnosti:
- Blagajnički nalozi (uplatnica/isplatnica) s numeracijom
- Limit gotovine 10.000 EUR (Zakon o fiskalizaciji čl. 28)
- Blagajnički izvještaj (dnevni rekapitulacija)
- Validacija: fizička osoba limit, blagajnički maksimum
- Tečajne razlike za deviznu blagajnu
- Reprezentacija upozorenja (30% nepriznato)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger("nyx_light.modules.blagajna")

# Zakonski limiti
GOTOVINSKI_LIMIT_EUR = 10_000.00   # Max gotovinski promet s jednim partnerom
BLAGAJNICKI_MAX_EUR = 15_000.00    # Preporučeni max saldo blagajne
FISKALIZACIJA_LIMIT = 15.00        # Ispod ovog iznosa nije obavezna fiskalizacija
REPREZENTACIJA_NEPRIZNATO_PCT = 0.30  # 30% troškova reprezentacije nepriznato


@dataclass
class BlagajnickiNalog:
    """Jedan blagajnički nalog (uplatnica ili isplatnica)."""
    redni_broj: int = 0
    datum: str = ""
    tip: str = ""              # "uplatnica" ili "isplatnica"
    opis: str = ""
    partner: str = ""
    partner_oib: str = ""
    iznos: float = 0.0
    konto_duguje: str = ""
    konto_potrazuje: str = ""
    kategorija: str = ""       # materijal, usluga, reprezentacija, placa, ostalo
    dokument_ref: str = ""     # Referenca na račun/dokument
    napomena: str = ""
    validacijske_greske: List[str] = field(default_factory=list)
    upozorenja: List[str] = field(default_factory=list)


@dataclass
class BlagajnickiIzvjestaj:
    """Dnevni blagajnički izvještaj."""
    datum: str = ""
    redni_broj_izvjestaja: int = 0
    prethodni_saldo: float = 0.0
    uplate: List[BlagajnickiNalog] = field(default_factory=list)
    isplate: List[BlagajnickiNalog] = field(default_factory=list)
    ukupno_uplate: float = 0.0
    ukupno_isplate: float = 0.0
    novi_saldo: float = 0.0
    odgovorna_osoba: str = ""
    napomene: List[str] = field(default_factory=list)


class BlagajnaValidator:
    """Upravljanje blagajnom i validacija gotovinskog prometa."""

    def __init__(self):
        self._nalog_counter = 0
        self._izvjestaj_counter = 0
        self._partner_totals: Dict[str, float] = {}  # OIB → ukupno ove godine
        self._current_saldo = 0.0
        self._nalozi_danas: List[BlagajnickiNalog] = []

    def kreiraj_nalog(
        self,
        tip: str,
        iznos: float,
        opis: str,
        partner: str = "",
        partner_oib: str = "",
        kategorija: str = "ostalo",
        dokument_ref: str = "",
        datum: str = "",
    ) -> BlagajnickiNalog:
        """Kreiraj i validiraj blagajnički nalog."""
        self._nalog_counter += 1

        if not datum:
            datum = date.today().isoformat()

        nalog = BlagajnickiNalog(
            redni_broj=self._nalog_counter,
            datum=datum,
            tip=tip.lower(),
            opis=opis,
            partner=partner,
            partner_oib=partner_oib,
            iznos=abs(iznos),
            kategorija=kategorija.lower(),
            dokument_ref=dokument_ref,
        )

        # Auto-kontiranje
        if tip.lower() == "uplatnica":
            nalog.konto_duguje = "1400"   # Blagajna
            nalog.konto_potrazuje = "1200" if "kupac" in opis.lower() else "2600"
        else:
            nalog.konto_duguje = self._auto_konto_rashod(kategorija, opis)
            nalog.konto_potrazuje = "1400"  # Blagajna

        # Validacije
        self._validate(nalog)

        # Update stanja
        if nalog.tip == "uplatnica":
            self._current_saldo += nalog.iznos
        else:
            self._current_saldo -= nalog.iznos

        self._nalozi_danas.append(nalog)

        # Update partner totals za godišnji limit
        if partner_oib:
            self._partner_totals[partner_oib] = (
                self._partner_totals.get(partner_oib, 0) + nalog.iznos
            )

        return nalog

    def _validate(self, nalog: BlagajnickiNalog):
        """Kompletna validacija blagajničkog naloga."""
        errors = nalog.validacijske_greske
        warnings = nalog.upozorenja

        # 1. Iznos validacija
        if nalog.iznos <= 0:
            errors.append("Iznos mora biti veći od 0")

        if nalog.iznos > GOTOVINSKI_LIMIT_EUR:
            errors.append(
                f"⛔ PREKRŠAJ: Gotovinski promet {nalog.iznos:.2f} EUR prelazi "
                f"zakonski limit od {GOTOVINSKI_LIMIT_EUR:.2f} EUR "
                f"(čl. 28 Zakona o fiskalizaciji)"
            )

        # 2. Partner godišnji limit
        if nalog.partner_oib:
            yearly = self._partner_totals.get(nalog.partner_oib, 0) + nalog.iznos
            if yearly > GOTOVINSKI_LIMIT_EUR:
                errors.append(
                    f"⛔ PREKRŠAJ: Ukupni gotovinski promet s partnerom "
                    f"(OIB: {nalog.partner_oib}) iznosi {yearly:.2f} EUR — "
                    f"prelazi godišnji limit od {GOTOVINSKI_LIMIT_EUR:.2f} EUR"
                )

        # 3. Saldo blagajne — negativan
        projected = self._current_saldo
        if nalog.tip == "isplatnica":
            projected -= nalog.iznos
        if projected < 0:
            errors.append(
                f"⛔ Isplata {nalog.iznos:.2f} EUR bi dovela blagajnu u minus "
                f"(trenutni saldo: {self._current_saldo:.2f} EUR)"
            )

        # 4. Preporučeni max saldo
        if nalog.tip == "uplatnica":
            projected = self._current_saldo + nalog.iznos
        if projected > BLAGAJNICKI_MAX_EUR:
            warnings.append(
                f"⚠️ Saldo blagajne ({projected:.2f} EUR) prelazi preporučeni "
                f"maksimum od {BLAGAJNICKI_MAX_EUR:.2f} EUR — preporuča se "
                f"polog na žiro račun"
            )

        # 5. Reprezentacija upozorenje
        if nalog.kategorija == "reprezentacija":
            nepriznato = round(nalog.iznos * REPREZENTACIJA_NEPRIZNATO_PCT, 2)
            warnings.append(
                f"⚠️ Reprezentacija: {nepriznato:.2f} EUR ({REPREZENTACIJA_NEPRIZNATO_PCT*100:.0f}%) "
                f"porezno nepriznato (čl. 7 st. 1 t. 3 Zakona o porezu na dobit)"
            )

        # 6. Fiskalizacija obaveza
        if nalog.tip == "uplatnica" and nalog.iznos >= FISKALIZACIJA_LIMIT:
            warnings.append("📋 Obavezna fiskalizacija za gotovinski primitak ≥15 EUR")

        # 7. OIB obavezan za iznose > 300 EUR
        if nalog.iznos > 300 and not nalog.partner_oib:
            warnings.append(
                "⚠️ Za iznose >300 EUR preporuča se evidentirati OIB partnera"
            )

    def _auto_konto_rashod(self, kategorija: str, opis: str) -> str:
        """Auto-kontiranje za isplatnice."""
        mapping = {
            "materijal": "4009",
            "uredski_materijal": "4091",
            "gorivo": "4070",
            "posta": "4050",
            "reprezentacija": "4094",
            "putovanje": "4093",
            "usluga": "4120",
            "sitan_inventar": "4092",
            "clanarina": "4097",
            "placa": "4500",
        }
        return mapping.get(kategorija, "4099")

    def generiraj_dnevni_izvjestaj(
        self, datum: str = "", prethodni_saldo: float = 0.0,
        odgovorna_osoba: str = "",
    ) -> BlagajnickiIzvjestaj:
        """Generiraj dnevni blagajnički izvještaj."""
        self._izvjestaj_counter += 1

        if not datum:
            datum = date.today().isoformat()

        uplate = [n for n in self._nalozi_danas if n.tip == "uplatnica"]
        isplate = [n for n in self._nalozi_danas if n.tip == "isplatnica"]

        ukupno_u = sum(n.iznos for n in uplate)
        ukupno_i = sum(n.iznos for n in isplate)

        izvjestaj = BlagajnickiIzvjestaj(
            datum=datum,
            redni_broj_izvjestaja=self._izvjestaj_counter,
            prethodni_saldo=prethodni_saldo,
            uplate=uplate,
            isplate=isplate,
            ukupno_uplate=round(ukupno_u, 2),
            ukupno_isplate=round(ukupno_i, 2),
            novi_saldo=round(prethodni_saldo + ukupno_u - ukupno_i, 2),
            odgovorna_osoba=odgovorna_osoba,
        )

        return izvjestaj

    def izvjestaj_to_dict(self, izvjestaj: BlagajnickiIzvjestaj) -> Dict[str, Any]:
        """Serijalizacija izvještaja za API/export."""
        return {
            "datum": izvjestaj.datum,
            "redni_broj": izvjestaj.redni_broj_izvjestaja,
            "prethodni_saldo": izvjestaj.prethodni_saldo,
            "uplate": [
                {"rb": n.redni_broj, "opis": n.opis, "partner": n.partner,
                 "iznos": n.iznos, "konto_d": n.konto_duguje, "konto_p": n.konto_potrazuje}
                for n in izvjestaj.uplate
            ],
            "isplate": [
                {"rb": n.redni_broj, "opis": n.opis, "partner": n.partner,
                 "iznos": n.iznos, "konto_d": n.konto_duguje, "konto_p": n.konto_potrazuje}
                for n in izvjestaj.isplate
            ],
            "ukupno_uplate": izvjestaj.ukupno_uplate,
            "ukupno_isplate": izvjestaj.ukupno_isplate,
            "novi_saldo": izvjestaj.novi_saldo,
            "broj_naloga": len(izvjestaj.uplate) + len(izvjestaj.isplate),
            "odgovorna_osoba": izvjestaj.odgovorna_osoba,
        }

    def validate_transaction(self, iznos: float, partner_oib: str = "") -> Dict[str, Any]:
        """Quick validacija — za API endpoint."""
        result = {"valid": True, "errors": [], "warnings": []}

        if iznos > GOTOVINSKI_LIMIT_EUR:
            result["valid"] = False
            result["errors"].append(
                f"Gotovinski limit {GOTOVINSKI_LIMIT_EUR} EUR prekoračen"
            )

        if partner_oib:
            yearly = self._partner_totals.get(partner_oib, 0) + iznos
            if yearly > GOTOVINSKI_LIMIT_EUR:
                result["valid"] = False
                result["errors"].append(
                    f"Godišnji limit s partnerom prekoračen ({yearly:.2f} EUR)"
                )

        projected = self._current_saldo - iznos
        if projected < 0:
            result["warnings"].append(
                f"Nedovoljno sredstava u blagajni (saldo: {self._current_saldo:.2f} EUR)"
            )

        return result

    def get_saldo(self) -> float:
        return round(self._current_saldo, 2)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "saldo": self.get_saldo(),
            "naloga_danas": len(self._nalozi_danas),
            "uplate_danas": sum(1 for n in self._nalozi_danas if n.tip == "uplatnica"),
            "isplate_danas": sum(1 for n in self._nalozi_danas if n.tip == "isplatnica"),
            "partnera_u_prometu": len(self._partner_totals),
            "limit_gotovine": GOTOVINSKI_LIMIT_EUR,
        }


# ═══════════════════════════════════════════
# BACKWARD COMPATIBILITY — BlagajnaTx, old validate_transaction
# (Consolidated — supports Sprint 7 and Sprint 15 test patterns)
# ═══════════════════════════════════════════

# Remove earlier BlagajnaTx if it was defined above — this one is authoritative
@dataclass
class BlagajnaTx:
    """Legacy transaction class for backward compatibility."""
    iznos: float = 0.0
    tip: str = "isplatnica"     # Sprint 7 style
    vrsta: str = ""             # Sprint 15 style
    redni_broj: int = 0
    opis: str = ""
    partner: str = ""
    partner_oib: str = ""
    kategorija: str = "ostalo"
    dokument_ref: str = ""

    def __post_init__(self):
        # Sync tip/vrsta
        if self.vrsta and not self.tip:
            self.tip = "uplatnica" if self.vrsta == "uplata" else "isplatnica"
        elif self.tip and not self.vrsta:
            self.vrsta = "uplata" if self.tip == "uplatnica" else "isplata"


@dataclass
class BlagajnaValidationResult:
    """Legacy validation result."""
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# Monkey-patch — unified validate_transaction
_base_validate_tx = BlagajnaValidator.validate_transaction

def _unified_validate_transaction(self, iznos_or_tx=None, partner_oib: str = "",
                                   current_balance=None, **kwargs):
    """Accept BlagajnaTx, float, or kwargs."""
    if isinstance(iznos_or_tx, BlagajnaTx):
        tx = iznos_or_tx
        check_balance = current_balance is not None
        balance = current_balance if check_balance else 999999

        r = BlagajnaValidationResult()
        errors = []
        warnings = []

        # AML limit (>= 10000)
        if tx.iznos >= GOTOVINSKI_LIMIT_EUR:
            errors.append(
                f"⛔ ZABRANA (AML čl. 30.): Gotovinski promet {tx.iznos:.2f} EUR "
                f"≥ {GOTOVINSKI_LIMIT_EUR:.2f} EUR"
            )

        # Negative balance
        vrsta = tx.vrsta or ("isplata" if tx.tip == "isplatnica" else "uplata")
        if check_balance and vrsta == "isplata" and balance - tx.iznos < 0:
            errors.append(f"Negativan saldo: {balance:.2f} - {tx.iznos:.2f} < 0")

        # Sequential gap
        if tx.redni_broj and hasattr(self, '_zadnji_rb') and self._zadnji_rb:
            if tx.redni_broj > self._zadnji_rb + 1:
                warnings.append(f"Praznina u numeraciji: {self._zadnji_rb} → {tx.redni_broj}")
            self._zadnji_rb = tx.redni_broj

        # Max balance
        if vrsta == "uplata" and balance + tx.iznos > GOTOVINSKI_LIMIT_EUR:
            warnings.append(f"Saldo prelazi max ({balance + tx.iznos:.2f} > {GOTOVINSKI_LIMIT_EUR:.2f})")

        r.valid = len(errors) == 0
        r.errors = errors
        r.warnings = warnings
        return r
    elif isinstance(iznos_or_tx, (int, float)):
        return _base_validate_tx(self, iznos=iznos_or_tx, partner_oib=partner_oib)
    else:
        return _base_validate_tx(self, **kwargs)

BlagajnaValidator.validate_transaction = _unified_validate_transaction
BlagajnaValidator._zadnji_rb = 0

def _compat_validate(self, iznos=0, tip="isplata", **kwargs):
    """Legacy validate() method."""
    result = _base_validate_tx(self, iznos=iznos)
    result["tip"] = tip
    return result

BlagajnaValidator.validate = _compat_validate

def _compat_validate_and_report(self, data):
    """Legacy validate_and_report() method."""
    iznos = data.get("iznos", 0)
    result = {"valid": True, "errors": [], "warnings": []}
    if iznos >= GOTOVINSKI_LIMIT_EUR:
        result["valid"] = False
        result["errors"].append(f"Prelazi limit od {GOTOVINSKI_LIMIT_EUR:.0f} EUR (10.000 EUR)")
    return result

BlagajnaValidator.validate_and_report = _compat_validate_and_report

def _compat_validate(self, iznos=0, tip="isplata", **kwargs):
    """Legacy validate() method."""
    result = _base_validate_tx(self, iznos=iznos)
    result["tip"] = tip
    return result

BlagajnaValidator.validate = _compat_validate

def _compat_validate_and_report(self, data):
    """Legacy validate_and_report() method."""
    iznos = data.get("iznos", 0)
    result = {"valid": True, "errors": [], "warnings": []}
    if iznos >= GOTOVINSKI_LIMIT_EUR:
        result["valid"] = False
        result["errors"].append(f"Prelazi limit od {GOTOVINSKI_LIMIT_EUR:.0f} EUR (10.000 EUR)")
    return result

BlagajnaValidator.validate_and_report = _compat_validate_and_report
