"""
Modul E2 — Pojašnjenje izvještaja

Kad klijent ili šef pita "Što znači ova bilanca?",
ovaj modul generira razumljivo objašnjenje financijskih izvještaja.

Podržani izvještaji:
  - Bilanca (aktiva/pasiva, likvidnost, zaduženost)
  - RDG (prihodi, rashodi, dobit/gubitak)
  - Bruto bilanca (saldo po kontima)
  - PDV prijava (ulazni/izlazni, obveza/povrat)
  - Novčani tokovi (operativni, investicijski, financijski)
  - KPI dashboard (trendovi, upozorenja)
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.communication")


@dataclass
class Explanation:
    """Generirano pojašnjenje izvještaja."""
    title: str
    summary: str
    key_points: List[str]
    warnings: List[str]
    recommendations: List[str]
    detail_level: str = "standard"  # simple, standard, expert
    target_audience: str = "klijent"  # klijent, menadzer, racunovodja


class ReportExplainer:
    """Generira razumljiva pojašnjenja financijskih izvještaja."""

    def __init__(self):
        self._explanations_count = 0

    def explain_bilanca(self, bilanca: Dict[str, Any],
                        period: str = "",
                        level: str = "standard") -> Explanation:
        """Objasni bilancu na razumljiv način."""
        aktiva = bilanca.get("aktiva_ukupno", 0)
        pasiva = bilanca.get("pasiva_ukupno", 0)
        kapital = bilanca.get("kapital", 0)
        obveze = bilanca.get("obveze_ukupno", 0)
        kratkorocne = bilanca.get("kratkorocne_obveze", 0)
        dugorocne = bilanca.get("dugorocne_obveze", 0)
        kratkot_imovina = bilanca.get("kratkotrajna_imovina", 0)

        points = []
        warnings = []
        recs = []

        # Veličina
        points.append(f"Ukupna imovina tvrtke iznosi {aktiva:,.2f} EUR")

        # Zaduženost
        if aktiva > 0:
            debt_ratio = obveze / aktiva
            if debt_ratio > 0.7:
                warnings.append(
                    f"Visoka zaduženost: {debt_ratio:.0%} imovine je financirano "
                    f"dugom. Preporuča se smanjenje obveza."
                )
            elif debt_ratio < 0.3:
                points.append(
                    f"Niska zaduženost ({debt_ratio:.0%}) — financijski stabilno"
                )

        # Likvidnost
        if kratkorocne > 0 and kratkot_imovina > 0:
            current_ratio = kratkot_imovina / kratkorocne
            if current_ratio < 1.0:
                warnings.append(
                    f"Tekući koeficijent {current_ratio:.2f} < 1 — "
                    f"kratkotrajna imovina ne pokriva kratkoročne obveze!"
                )
                recs.append("Razmotriti refinanciranje kratkoročnih obveza")
            elif current_ratio > 2.0:
                points.append(
                    f"Odlična likvidnost (koef. {current_ratio:.2f})"
                )

        # Kapital
        if kapital < 0:
            warnings.append("Negativan kapital — tvrtka ima gubitak iznad uloženog")
            recs.append("Hitno: dokapitalizacija ili smanjenje gubitaka")
        elif kapital > 0:
            points.append(f"Vlastiti kapital: {kapital:,.2f} EUR")

        summary = (
            f"Bilanca za {period or 'tekući period'}: "
            f"Imovina {aktiva:,.2f} EUR, "
            f"Kapital {kapital:,.2f} EUR, "
            f"Obveze {obveze:,.2f} EUR."
        )

        self._explanations_count += 1
        return Explanation(
            title=f"Bilanca — {period}" if period else "Bilanca",
            summary=summary,
            key_points=points,
            warnings=warnings,
            recommendations=recs,
            detail_level=level,
        )

    def explain_rdg(self, rdg: Dict[str, Any],
                    period: str = "",
                    level: str = "standard") -> Explanation:
        """Objasni račun dobiti i gubitka."""
        prihodi = rdg.get("prihodi_ukupno", 0)
        rashodi = rdg.get("rashodi_ukupno", 0)
        dobit = rdg.get("dobit_prije_poreza", prihodi - rashodi)
        porez = rdg.get("porez_na_dobit", 0)
        neto = dobit - porez
        marza = (dobit / prihodi * 100) if prihodi > 0 else 0

        points = []
        warnings = []
        recs = []

        points.append(f"Ukupni prihodi: {prihodi:,.2f} EUR")
        points.append(f"Ukupni rashodi: {rashodi:,.2f} EUR")

        if neto > 0:
            points.append(f"Neto dobit: {neto:,.2f} EUR (marža {marza:.1f}%)")
        else:
            warnings.append(f"Gubitak: {abs(neto):,.2f} EUR")
            recs.append("Analiziraj strukturu rashoda za uštede")

        if marza < 5 and prihodi > 0:
            warnings.append(f"Niska profitna marža ({marza:.1f}%)")
        elif marza > 20:
            points.append("Visoka profitabilnost")

        summary = (
            f"{'Dobit' if neto >= 0 else 'Gubitak'} za {period}: "
            f"{abs(neto):,.2f} EUR "
            f"(prihodi {prihodi:,.2f}, rashodi {rashodi:,.2f})"
        )

        self._explanations_count += 1
        return Explanation(
            title=f"RDG — {period}" if period else "Račun dobiti i gubitka",
            summary=summary,
            key_points=points,
            warnings=warnings,
            recommendations=recs,
            detail_level=level,
        )

    def explain_pdv(self, pdv: Dict[str, Any],
                    period: str = "") -> Explanation:
        """Objasni PDV prijavu."""
        ulazni = pdv.get("pretporez_ukupno", 0)
        izlazni = pdv.get("obveza_ukupno", 0)
        razlika = izlazni - ulazni

        points = [
            f"Izlazni PDV (obveza): {izlazni:,.2f} EUR",
            f"Ulazni PDV (pretporez): {ulazni:,.2f} EUR",
        ]
        warnings = []

        if razlika > 0:
            points.append(f"Za uplatu Poreznoj: {razlika:,.2f} EUR")
        else:
            points.append(f"Povrat od Porezne: {abs(razlika):,.2f} EUR")

        if abs(razlika) > 50000:
            warnings.append("Veliki iznos — moguća porezna kontrola")

        self._explanations_count += 1
        return Explanation(
            title=f"PDV prijava — {period}",
            summary=f"{'Obveza' if razlika > 0 else 'Povrat'}: "
                    f"{abs(razlika):,.2f} EUR",
            key_points=points,
            warnings=warnings,
            recommendations=[],
        )

    def explain_cashflow(self, cashflow: Dict[str, Any],
                         period: str = "") -> Explanation:
        """Objasni novčani tok."""
        op = cashflow.get("operativni", 0)
        inv = cashflow.get("investicijski", 0)
        fin = cashflow.get("financijski", 0)
        neto = op + inv + fin

        points = [
            f"Operativni: {op:+,.2f} EUR",
            f"Investicijski: {inv:+,.2f} EUR",
            f"Financijski: {fin:+,.2f} EUR",
            f"Neto promjena: {neto:+,.2f} EUR",
        ]
        warnings = []
        recs = []

        if op < 0:
            warnings.append("Negativan operativni tok — osnovni biznis troši novac")
            recs.append("Ubrzaj naplatu potraživanja, pregovaraj duže rokove plaćanja")

        self._explanations_count += 1
        return Explanation(
            title=f"Novčani tokovi — {period}",
            summary=f"Neto tok: {neto:+,.2f} EUR",
            key_points=points,
            warnings=warnings,
            recommendations=recs,
        )

    def to_text(self, exp: Explanation) -> str:
        """Pretvori Explanation u čitljiv tekst."""
        lines = [f"📊 {exp.title}", "", exp.summary, ""]
        if exp.key_points:
            lines.append("Ključne točke:")
            for p in exp.key_points:
                lines.append(f"  ✅ {p}")
        if exp.warnings:
            lines.append("\nUpozorenja:")
            for w in exp.warnings:
                lines.append(f"  ⚠️ {w}")
        if exp.recommendations:
            lines.append("\nPreporuke:")
            for r in exp.recommendations:
                lines.append(f"  💡 {r}")
        return "\n".join(lines)

    def get_stats(self):
        return {"explanations_generated": self._explanations_count}
