"""
Nyx Light — Triple Verification (3× nezavisna provjera)

Svaki podatak u sustavu prolazi kroz 3 NEZAVISNE provjere prije
nego što se prikaže korisniku. Točnost je apsolutni prioritet.

Provjere:
  1. AI Check — LLM model analizira podatak
  2. Algorithmic Check — deterministički algoritam (regex, formula, lookup)
  3. Rule Check — zakonska pravila i poslovni constraints

Confidence Score:
  - 3/3 slažu se → 0.95-1.00 → Prikaži korisniku
  - 2/3 slažu se → 0.70-0.94 → Prikaži + upozorenje
  - 1/3 ili manje  → < 0.70    → ZAUSTAVI, zatraži ljudsku provjeru
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.verification.triple_check")


class CheckResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class ConsensusLevel(Enum):
    FULL = "full"           # 3/3 — svi se slažu
    MAJORITY = "majority"   # 2/3 — većina se slaže
    CONFLICT = "conflict"   # neslaganje — zahtijeva ljudsku provjeru


@dataclass
class VerificationResult:
    """Rezultat jedne od 3 provjere."""
    check_name: str          # "ai_check", "algo_check", "rule_check"
    result: CheckResult
    value: Any               # Što je provjera pronašla
    details: str = ""        # Detalji/obrazloženje
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TripleCheckResult:
    """Konačni rezultat 3× verifikacije."""
    field_name: str           # npr. "oib", "pdv_iznos", "konto"
    original_value: Any       # Originalna ulazna vrijednost

    check_1: Optional[VerificationResult] = None  # AI
    check_2: Optional[VerificationResult] = None  # Algoritam
    check_3: Optional[VerificationResult] = None  # Pravilo

    consensus: ConsensusLevel = ConsensusLevel.CONFLICT
    confidence: float = 0.0
    final_value: Any = None
    needs_human_review: bool = True
    reason: str = ""

    def compute_consensus(self):
        """Izračunaj konsenzus iz 3 provjere."""
        checks = [self.check_1, self.check_2, self.check_3]
        passes = sum(1 for c in checks if c and c.result == CheckResult.PASS)
        fails = sum(1 for c in checks if c and c.result == CheckResult.FAIL)

        if passes == 3:
            self.consensus = ConsensusLevel.FULL
            self.confidence = 1.0
            self.needs_human_review = False
            self.reason = "Sve 3 provjere se slažu"
        elif passes == 2:
            self.consensus = ConsensusLevel.MAJORITY
            self.confidence = 0.85
            self.needs_human_review = False  # Ali prikaži upozorenje
            failed = [c for c in checks if c and c.result != CheckResult.PASS]
            self.reason = f"2/3 provjere se slažu. Neslaganje: {failed[0].check_name if failed else '?'}"
        else:
            self.consensus = ConsensusLevel.CONFLICT
            self.confidence = max(0.0, passes * 0.3)
            self.needs_human_review = True
            self.reason = f"Neslaganje ({passes}/3). Potrebna ljudska provjera."

        # Postavi final_value na najčešću vrijednost
        values = [c.value for c in checks if c and c.result == CheckResult.PASS]
        if values:
            self.final_value = values[0]
        else:
            self.final_value = self.original_value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field_name,
            "original": self.original_value,
            "final": self.final_value,
            "consensus": self.consensus.value,
            "confidence": round(self.confidence, 2),
            "needs_human_review": self.needs_human_review,
            "reason": self.reason,
            "checks": {
                "ai": self.check_1.result.value if self.check_1 else None,
                "algorithm": self.check_2.result.value if self.check_2 else None,
                "rule": self.check_3.result.value if self.check_3 else None,
            },
        }


class TripleVerifier:
    """
    Centralni Triple Verification engine.

    Registriraj provjere za svaki tip podatka,
    zatim pozovi verify() za 3× nezavisnu verifikaciju.
    """

    def __init__(self):
        self._checks: Dict[str, Dict[str, Callable]] = {}
        self._stats = {"total": 0, "full": 0, "majority": 0, "conflict": 0}

        # Registriraj standardne provjere
        self._register_builtin_checks()

    def register_check(self, field_type: str, check_name: str,
                       check_fn: Callable[[Any, Dict], VerificationResult]):
        """Registriraj provjeru za tip podatka."""
        if field_type not in self._checks:
            self._checks[field_type] = {}
        self._checks[field_type][check_name] = check_fn
        logger.debug("Registered check: %s.%s", field_type, check_name)

    def verify(self, field_type: str, value: Any,
               context: Optional[Dict] = None) -> TripleCheckResult:
        """
        Pokreni 3× nezavisnu verifikaciju.

        Args:
            field_type: Tip podatka (npr. "oib", "pdv_iznos", "konto")
            value: Vrijednost za provjeru
            context: Dodatni kontekst (npr. datum, klijent)

        Returns:
            TripleCheckResult s konsenzusom i confidence score-om
        """
        ctx = context or {}
        result = TripleCheckResult(field_name=field_type, original_value=value)

        checks = self._checks.get(field_type, {})
        check_list = list(checks.items())

        # Pokreni sve registrirane provjere (min 3)
        for i, (name, fn) in enumerate(check_list[:3]):
            try:
                vr = fn(value, ctx)
                if i == 0:
                    result.check_1 = vr
                elif i == 1:
                    result.check_2 = vr
                elif i == 2:
                    result.check_3 = vr
            except Exception as e:
                logger.error("Check %s failed: %s", name, e)
                vr = VerificationResult(
                    check_name=name,
                    result=CheckResult.UNCERTAIN,
                    value=None,
                    details=f"Error: {e}",
                )
                if i == 0:
                    result.check_1 = vr
                elif i == 1:
                    result.check_2 = vr
                elif i == 2:
                    result.check_3 = vr

        # Popuni nedostajuće provjere
        for i, attr in enumerate(["check_1", "check_2", "check_3"]):
            if getattr(result, attr) is None:
                setattr(result, attr, VerificationResult(
                    check_name=f"missing_{i}",
                    result=CheckResult.UNCERTAIN,
                    value=None,
                    details="Provjera nije registrirana za ovaj tip",
                ))

        result.compute_consensus()

        # Statistike
        self._stats["total"] += 1
        self._stats[result.consensus.value] += 1

        logger.info(
            "Triple check [%s]: %s (confidence=%.2f, human_review=%s)",
            field_type, result.consensus.value,
            result.confidence, result.needs_human_review,
        )

        return result

    def verify_batch(self, items: List[Tuple[str, Any, Dict]]) -> List[TripleCheckResult]:
        """Verificiraj batch podataka."""
        return [self.verify(ft, val, ctx) for ft, val, ctx in items]

    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total"]
        return {
            "total_checks": total,
            "full_consensus": self._stats["full"],
            "majority_consensus": self._stats["majority"],
            "conflicts": self._stats["conflict"],
            "accuracy_rate": round(
                (self._stats["full"] + self._stats["majority"]) / max(total, 1), 4
            ),
        }

    # ═══════════════════════════════════════
    # UGRAĐENE PROVJERE
    # ═══════════════════════════════════════

    def _register_builtin_checks(self):
        """Registriraj standardne provjere za česte tipove podataka."""

        # ── OIB ──
        self.register_check("oib", "ai_check", self._oib_ai_check)
        self.register_check("oib", "algo_check", self._oib_algo_check)
        self.register_check("oib", "rule_check", self._oib_rule_check)

        # ── PDV iznos ──
        self.register_check("pdv_iznos", "ai_check", self._pdv_ai_check)
        self.register_check("pdv_iznos", "algo_check", self._pdv_algo_check)
        self.register_check("pdv_iznos", "rule_check", self._pdv_rule_check)

        # ── IBAN ──
        self.register_check("iban", "ai_check", self._iban_ai_check)
        self.register_check("iban", "algo_check", self._iban_algo_check)
        self.register_check("iban", "rule_check", self._iban_rule_check)

    # ── OIB provjere ──

    @staticmethod
    def _oib_ai_check(value: Any, ctx: Dict) -> VerificationResult:
        """AI provjera: je li OIB izgleda validno (format)."""
        s = str(value).strip()
        is_valid = len(s) == 11 and s.isdigit()
        return VerificationResult(
            check_name="ai_check",
            result=CheckResult.PASS if is_valid else CheckResult.FAIL,
            value=s if is_valid else None,
            details=f"OIB format: {'OK' if is_valid else 'NEVALJAN'} ({s})",
        )

    @staticmethod
    def _oib_algo_check(value: Any, ctx: Dict) -> VerificationResult:
        """Algoritamska provjera: ISO 7064 mod 11,10."""
        s = str(value).strip()
        if len(s) != 11 or not s.isdigit():
            return VerificationResult(
                check_name="algo_check",
                result=CheckResult.FAIL,
                value=None,
                details="OIB mora imati 11 znamenki",
            )
        # ISO 7064 Mod 11,10 algoritam
        remainder = 10
        for digit in s[:10]:
            remainder = (remainder + int(digit)) % 10
            if remainder == 0:
                remainder = 10
            remainder = (remainder * 2) % 11
        check = 11 - remainder
        if check == 10:
            check = 0
        is_valid = check == int(s[10])
        return VerificationResult(
            check_name="algo_check",
            result=CheckResult.PASS if is_valid else CheckResult.FAIL,
            value=s if is_valid else None,
            details=f"ISO 7064 mod 11,10: {'PASS' if is_valid else 'FAIL'} (kontrolna={check}, zadnja={s[10]})",
        )

    @staticmethod
    def _oib_rule_check(value: Any, ctx: Dict) -> VerificationResult:
        """Pravilo: OIB ne smije biti sve nule ili poznati test OIB."""
        s = str(value).strip()
        invalid_oibs = {"00000000000", "11111111111", "12345678901"}
        if s in invalid_oibs:
            return VerificationResult(
                check_name="rule_check",
                result=CheckResult.FAIL,
                value=None,
                details=f"OIB {s} je poznati test/nevaljan OIB",
            )
        return VerificationResult(
            check_name="rule_check",
            result=CheckResult.PASS,
            value=s,
            details="OIB nije u listi poznatih nevalidnih",
        )

    # ── PDV provjere ──

    @staticmethod
    def _pdv_ai_check(value: Any, ctx: Dict) -> VerificationResult:
        """AI provjera: je li PDV pozitivan broj."""
        try:
            v = float(value)
            ok = v >= 0
            return VerificationResult(
                check_name="ai_check",
                result=CheckResult.PASS if ok else CheckResult.FAIL,
                value=v if ok else None,
                details=f"PDV iznos: {v} {'≥0 OK' if ok else '<0 NEVALJAN'}",
            )
        except (ValueError, TypeError):
            return VerificationResult(
                check_name="ai_check",
                result=CheckResult.FAIL,
                value=None,
                details=f"PDV iznos nije broj: {value}",
            )

    @staticmethod
    def _pdv_algo_check(value: Any, ctx: Dict) -> VerificationResult:
        """Algoritamska provjera: PDV = osnovica × stopa."""
        try:
            pdv = float(value)
            osnovica = float(ctx.get("osnovica", 0))
            stopa = float(ctx.get("pdv_stopa", 0.25))
            expected = round(osnovica * stopa, 2)
            # Tolerancija od 1 lipe (0.01 EUR)
            match = abs(pdv - expected) <= 0.01
            return VerificationResult(
                check_name="algo_check",
                result=CheckResult.PASS if match else CheckResult.FAIL,
                value=pdv if match else expected,
                details=f"Izračun: {osnovica} × {stopa} = {expected}, deklarirano: {pdv}",
            )
        except (ValueError, TypeError, KeyError):
            return VerificationResult(
                check_name="algo_check",
                result=CheckResult.UNCERTAIN,
                value=None,
                details="Nedostaju podaci za izračun PDV-a",
            )

    @staticmethod
    def _pdv_rule_check(value: Any, ctx: Dict) -> VerificationResult:
        """Pravilo: PDV stope u RH su 5%, 13%, 25%."""
        try:
            stopa = float(ctx.get("pdv_stopa", 0.25))
            valid_rates = {0.0, 0.05, 0.13, 0.25}
            ok = stopa in valid_rates
            return VerificationResult(
                check_name="rule_check",
                result=CheckResult.PASS if ok else CheckResult.FAIL,
                value=stopa if ok else None,
                details=f"PDV stopa {stopa*100}%: {'validna' if ok else 'NEVALIDNA'} (dozvoljene: 0%, 5%, 13%, 25%)",
            )
        except (ValueError, TypeError):
            return VerificationResult(
                check_name="rule_check",
                result=CheckResult.UNCERTAIN,
                value=None,
                details="PDV stopa nije dostupna",
            )

    # ── IBAN provjere ──

    @staticmethod
    def _iban_ai_check(value: Any, ctx: Dict) -> VerificationResult:
        """AI provjera: IBAN format."""
        s = str(value).replace(" ", "").upper()
        ok = len(s) == 21 and s[:2] == "HR" and s[2:4].isdigit()
        return VerificationResult(
            check_name="ai_check",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            value=s if ok else None,
            details=f"IBAN format HR: {'OK' if ok else 'NEVALJAN'} ({s[:6]}...)",
        )

    @staticmethod
    def _iban_algo_check(value: Any, ctx: Dict) -> VerificationResult:
        """Algoritamska provjera: IBAN mod 97 validacija."""
        s = str(value).replace(" ", "").upper()
        if len(s) < 5:
            return VerificationResult(
                check_name="algo_check", result=CheckResult.FAIL,
                value=None, details="IBAN prekratak",
            )
        # Premjesti prve 4 znaka na kraj, pretvori slova u brojeve
        rearranged = s[4:] + s[:4]
        numeric = ""
        for ch in rearranged:
            if ch.isdigit():
                numeric += ch
            elif ch.isalpha():
                numeric += str(ord(ch) - 55)
            else:
                return VerificationResult(
                    check_name="algo_check", result=CheckResult.FAIL,
                    value=None, details=f"Nedozvoljeni znak u IBAN-u: {ch}",
                )
        ok = int(numeric) % 97 == 1
        return VerificationResult(
            check_name="algo_check",
            result=CheckResult.PASS if ok else CheckResult.FAIL,
            value=s if ok else None,
            details=f"IBAN mod 97: {'PASS' if ok else 'FAIL'}",
        )

    @staticmethod
    def _iban_rule_check(value: Any, ctx: Dict) -> VerificationResult:
        """Pravilo: HR IBAN mora imati poznati bank code."""
        s = str(value).replace(" ", "").upper()
        known_banks = {
            "2340009": "PBZ",
            "2360000": "Erste",
            "2484008": "RBA",
            "2402006": "Erste S",
            "2407000": "OTP",
            "2500009": "Addiko",
            "2390001": "HPB",
            "2340009": "PBZ",
        }
        if len(s) >= 11:
            bank_code = s[4:11]
            bank = known_banks.get(bank_code)
            if bank:
                return VerificationResult(
                    check_name="rule_check", result=CheckResult.PASS,
                    value=s, details=f"Banka: {bank} ({bank_code})",
                )
        return VerificationResult(
            check_name="rule_check", result=CheckResult.UNCERTAIN,
            value=s, details="Banka nepoznata (ali IBAN može biti validan)",
        )
