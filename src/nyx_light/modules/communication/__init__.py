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

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.communication")


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


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Email templating za IOS, opomene, obavijesti klijentima
# ════════════════════════════════════════════════════════

from datetime import date


PREDLOSCI = {
    "ios_slanje": {
        "subject": "IOS Usklađivanje stanja na dan {datum}",
        "body": (
            "Poštovani,\n\n"
            "U privitku dostavljamo Izvod Otvorenih Stavki (IOS) na dan {datum}.\n"
            "Molimo Vas da nam u roku od {rok} dana potvrdite stanje ili dostavite "
            "Vaš IOS radi usklađivanja.\n\n"
            "Naše potraživanje prema Vama iznosi: {iznos_potrazivanja} EUR\n"
            "Naša obveza prema Vama iznosi: {iznos_obveza} EUR\n\n"
            "S poštovanjem,\n{potpis}"
        ),
    },
    "opomena_1": {
        "subject": "Opomena za dospjele fakture — {partner_naziv}",
        "body": (
            "Poštovani,\n\n"
            "Ovim putem Vas ljubazno podsjećamo da imate neplaćene fakture:\n\n"
            "{fakture_lista}\n"
            "Ukupan dospjeli iznos: {ukupno_dospjelo} EUR\n\n"
            "Molimo uplatu u najkraćem mogućem roku na IBAN: {iban}\n"
            "Poziv na broj: {poziv_na_broj}\n\n"
            "S poštovanjem,\n{potpis}"
        ),
    },
    "opomena_2": {
        "subject": "DRUGA OPOMENA — Dospjele fakture {partner_naziv}",
        "body": (
            "Poštovani,\n\n"
            "Unatoč našoj prvoj opomeni od {datum_prve_opomene}, "
            "do danas nismo primili uplatu za sljedeće fakture:\n\n"
            "{fakture_lista}\n"
            "Ukupan dospjeli iznos: {ukupno_dospjelo} EUR\n"
            "Kašnjenje: {dani_kasnjenja} dana\n\n"
            "Ukoliko ne primimo uplatu u roku od 8 dana, "
            "bit ćemo prisiljeni pokrenuti postupak prisilne naplate.\n\n"
            "S poštovanjem,\n{potpis}"
        ),
    },
    "zatezna_kamata": {
        "subject": "Obračun zatezne kamate — {partner_naziv}",
        "body": (
            "Poštovani,\n\n"
            "Obavještavamo Vas da Vam je temeljem čl. 29. Zakona o obveznim odnosima "
            "obračunata zatezna kamata na nepravodobno plaćene obveze:\n\n"
            "Osnovni dug: {osnovni_dug} EUR\n"
            "Stopa zatezne kamate: {stopa}% godišnje\n"
            "Razdoblje: {od_datuma} — {do_datuma} ({dani} dana)\n"
            "Zatezna kamata: {kamata} EUR\n"
            "Ukupno za uplatu: {ukupno} EUR\n\n"
            "S poštovanjem,\n{potpis}"
        ),
    },
}


class CommunicationEngine:
    """Generiranje poslovne korespondencije za računovodstvo."""

    def __init__(self):
        self._count = 0

    def generate_email(self, template_key: str, params: dict) -> dict:
        """Generiraj email iz predloška."""
        tpl = PREDLOSCI.get(template_key)
        if not tpl:
            return {"error": f"Nepoznat predložak: {template_key}", "available": list(PREDLOSCI.keys())}

        try:
            subject = tpl["subject"].format(**params)
            body = tpl["body"].format(**params)
        except KeyError as e:
            return {"error": f"Nedostaje parametar: {e}", "required_params": self._extract_params(tpl)}

        self._count += 1
        return {
            "subject": subject,
            "body": body,
            "template": template_key,
            "requires_review": True,
            "note": "Pregledajte sadržaj prije slanja.",
        }

    def izracun_zatezne_kamate(
        self,
        iznos_duga: float,
        datum_dospijeca: str,
        datum_obracuna: str = "",
        stopa_godisnja: float = 5.75,  # HNB referentna + 3pp (2026.)
    ) -> dict:
        """Izračun zatezne kamate prema ZOO čl. 29."""
        try:
            dospijece = date.fromisoformat(datum_dospijeca)
            obracun = date.fromisoformat(datum_obracuna) if datum_obracuna else date.today()
        except ValueError:
            return {"error": "Neispravan format datuma (YYYY-MM-DD)"}

        dani = max(0, (obracun - dospijece).days)
        kamata = _r2(_d(iznos_duga) * _d(stopa_godisnja) / _d(100) * _d(dani) / _d(365))

        return {
            "osnovni_dug": _r2(_d(iznos_duga)),
            "datum_dospijeca": datum_dospijeca,
            "datum_obracuna": obracun.isoformat(),
            "dani_kasnjenja": dani,
            "stopa_godisnja_pct": stopa_godisnja,
            "zatezna_kamata": kamata,
            "ukupno_za_uplatu": _r2(_d(iznos_duga) + _d(kamata)),
            "zakonski_temelj": "ZOO čl. 29, stopa: ESB referentna + 3pp",
        }

    @staticmethod
    def _extract_params(tpl: dict) -> list:
        import re
        all_text = tpl.get("subject", "") + tpl.get("body", "")
        return sorted(set(re.findall(r'\{(\w+)\}', all_text)))

    def get_stats(self):
        return {"emails_generated": self._count}
