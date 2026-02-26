"""
Nyx Light — Modul A5: Blagajna (Enhanced V2)

Provjere: AML limit, fiskalizacija, sekvencijalnost, stanje blagajne.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.blagajna")
MAX_CASH_BALANCE = 10_000.0
AML_SINGLE_TX_LIMIT = 10_000.0

@dataclass
class BlagajnaTx:
    redni_broj: int = 0
    datum: str = ""
    vrsta: str = "isplata"
    iznos: float = 0.0
    opis: str = ""
    partner: str = ""
    oib: str = ""
    fiskalni_broj: str = ""

@dataclass
class BlagajnaValidationResult:
    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stanje_nakon: float = 0.0

class BlagajnaValidator:
    """Validator za blagajničke operacije — Enhanced V2."""
    def __init__(self):
        self._stanje: float = 0.0
        self._zadnji_rb: int = 0
        self._count = 0

    def validate(self, iznos: float = 0, tip: str = "isplata", **kw) -> Dict[str, Any]:
        """Legacy API — backward compatible."""
        tx = BlagajnaTx(iznos=iznos, vrsta=tip)
        r = self.validate_transaction(tx)
        return {"valid": r.valid, "warnings": r.errors + r.warnings, "iznos": iznos}

    def validate_transaction(self, tx: BlagajnaTx, current_balance: float = None) -> BlagajnaValidationResult:
        result = BlagajnaValidationResult()
        bal = current_balance if current_balance is not None else self._stanje

        if tx.iznos >= AML_SINGLE_TX_LIMIT:
            result.errors.append(f"⛔ Gotovinska tx {tx.iznos:.2f} EUR >= {AML_SINGLE_TX_LIMIT:.0f} EUR — ZABRANA (AML čl. 30.)")
            result.valid = False

        if tx.redni_broj > 0 and self._zadnji_rb > 0:
            if tx.redni_broj != self._zadnji_rb + 1:
                result.warnings.append(f"⚠️ Praznina: očekivan {self._zadnji_rb+1}, dobiven {tx.redni_broj}")

        new_bal = bal - tx.iznos if tx.vrsta == "isplata" else bal + tx.iznos
        # Samo provjeri stanje ako je poznato (current_balance eksplicitno zadan)
        if current_balance is not None:
            if new_bal < 0:
                result.errors.append(f"⛔ Stanje negativno: {new_bal:.2f} EUR")
                result.valid = False
            if new_bal > MAX_CASH_BALANCE:
                result.warnings.append(f"⚠️ Stanje {new_bal:.2f} > max {MAX_CASH_BALANCE:.0f} EUR")
        result.stanje_nakon = new_bal

        if tx.vrsta == "uplata" and not tx.fiskalni_broj:
            result.warnings.append("⚠️ Uplata bez JIR/ZKI — fiskalizacija?")

        if result.valid:
            self._stanje = new_bal
            if tx.redni_broj > 0: self._zadnji_rb = tx.redni_broj
        self._count += 1
        return result

    def validate_batch(self, transactions: List[BlagajnaTx], opening: float = 0.0) -> Dict:
        self._stanje = opening
        details, errs = [], 0
        for tx in transactions:
            vr = self.validate_transaction(tx)
            details.append({"rb": tx.redni_broj, "valid": vr.valid, "stanje": vr.stanje_nakon, "errors": vr.errors, "warnings": vr.warnings})
            errs += len(vr.errors)
        return {"tx_count": len(transactions), "closing": self._stanje, "errors": errs, "ok": errs == 0, "details": details}

    def get_stats(self): return {"validations": self._count, "balance": self._stanje}
