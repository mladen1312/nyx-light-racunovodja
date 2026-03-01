"""
Modul G2 — Upravljačko Računovodstvo

Analitika za menadžersko odlučivanje:
  - Profitabilnost po segmentima (klijenti, usluge, proizvodi)
  - Break-even analiza
  - Cost center tracking
  - Budget vs Actual
  - Trendovi i projekcije
  - ABC analiza (Pareto klijenata)
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.modules.management_accounting")


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
class Segment:
    """Jedan poslovni segment za analizu."""
    name: str
    prihodi: float = 0.0
    varijabilni_troskovi: float = 0.0
    fiksni_troskovi: float = 0.0

    @property
    def kontribucijska_marza(self) -> float:
        return self.prihodi - self.varijabilni_troskovi

    @property
    def dobit(self) -> float:
        return self.kontribucijska_marza - self.fiksni_troskovi

    @property
    def marza_pct(self) -> float:
        return (self.kontribucijska_marza / self.prihodi * 100
                if self.prihodi > 0 else 0)


@dataclass
class BudgetLine:
    """Jedna linija budgeta."""
    konto: str
    naziv: str
    budget: float = 0.0
    actual: float = 0.0

    @property
    def variance(self) -> float:
        return self.actual - self.budget

    @property
    def variance_pct(self) -> float:
        return (self.variance / self.budget * 100
                if self.budget != 0 else 0)


class ManagementAccounting:
    """Upravljačko računovodstvo — analitika za odlučivanje."""

    def __init__(self):
        self._segments: Dict[str, Segment] = {}
        self._budgets: Dict[str, List[BudgetLine]] = {}
        self._cost_centers: Dict[str, Dict[str, float]] = {}

    # ════════════════════════════════════════
    # BREAK-EVEN ANALIZA
    # ════════════════════════════════════════

    def break_even(self, fiksni_troskovi: float,
                   cijena_po_jedinici: float,
                   varijabilni_po_jedinici: float) -> Dict[str, Any]:
        """Izračunaj break-even point."""
        if cijena_po_jedinici <= varijabilni_po_jedinici:
            return {"ok": False,
                    "error": "Cijena mora biti veća od varijabilnog troška"}

        kontribucija = cijena_po_jedinici - varijabilni_po_jedinici
        be_jedinice = math.ceil(fiksni_troskovi / kontribucija)
        be_prihod = be_jedinice * cijena_po_jedinici
        marza_pct = kontribucija / cijena_po_jedinici * 100

        return {
            "ok": True,
            "break_even_jedinice": be_jedinice,
            "break_even_prihod": round(be_prihod, 2),
            "kontribucija_po_jedinici": round(kontribucija, 2),
            "kontribucijska_marza_pct": round(marza_pct, 1),
            "fiksni_troskovi": fiksni_troskovi,
            "safety_margin_note": "Svaka jedinica iznad BE je čista dobit",
        }

    # ════════════════════════════════════════
    # PROFITABILNOST PO SEGMENTIMA
    # ════════════════════════════════════════

    def add_segment(self, name: str, prihodi: float,
                    varijabilni: float, fiksni: float = 0):
        """Dodaj poslovni segment."""
        self._segments[name] = Segment(
            name=name, prihodi=prihodi,
            varijabilni_troskovi=varijabilni,
            fiksni_troskovi=fiksni,
        )

    def analyze_segments(self) -> Dict[str, Any]:
        """Analiziraj profitabilnost svih segmenata."""
        if not self._segments:
            return {"ok": False, "error": "Nema segmenata"}

        results = []
        total_prihodi = 0
        total_dobit = 0

        for seg in sorted(self._segments.values(),
                          key=lambda s: s.dobit, reverse=True):
            results.append({
                "segment": seg.name,
                "prihodi": seg.prihodi,
                "kontribucija": round(seg.kontribucijska_marza, 2),
                "marza_pct": round(seg.marza_pct, 1),
                "dobit": round(seg.dobit, 2),
                "profitable": seg.dobit > 0,
            })
            total_prihodi += seg.prihodi
            total_dobit += seg.dobit

        return {
            "ok": True,
            "segments": results,
            "total_prihodi": round(total_prihodi, 2),
            "total_dobit": round(total_dobit, 2),
            "best": results[0]["segment"] if results else None,
            "worst": results[-1]["segment"] if results else None,
            "unprofitable": [r["segment"] for r in results if not r["profitable"]],
        }

    # ════════════════════════════════════════
    # ABC ANALIZA (Pareto)
    # ════════════════════════════════════════

    def abc_analysis(self, items: List[Tuple[str, float]]
                     ) -> Dict[str, List[str]]:
        """ABC analiza — 80/20 pravilo.

        Args:
            items: Lista (naziv, vrijednost) parova

        Returns:
            {"A": [...], "B": [...], "C": [...]}
            A = top 80% vrijednosti
            B = sljedećih 15%
            C = zadnjih 5%
        """
        sorted_items = sorted(items, key=lambda x: x[1], reverse=True)
        total = sum(v for _, v in sorted_items)
        if total == 0:
            return {"A": [], "B": [], "C": []}

        cumulative = 0
        result = {"A": [], "B": [], "C": []}

        for name, value in sorted_items:
            cumulative += value
            pct = cumulative / total
            if pct <= 0.8:
                result["A"].append(name)
            elif pct <= 0.95:
                result["B"].append(name)
            else:
                result["C"].append(name)

        return result

    # ════════════════════════════════════════
    # BUDGET vs ACTUAL
    # ════════════════════════════════════════

    def set_budget(self, period: str, lines: List[Dict[str, Any]]):
        """Postavi budget za period."""
        self._budgets[period] = [
            BudgetLine(
                konto=l.get("konto", ""),
                naziv=l.get("naziv", ""),
                budget=l.get("budget", 0),
                actual=l.get("actual", 0),
            )
            for l in lines
        ]

    def budget_vs_actual(self, period: str) -> Dict[str, Any]:
        """Usporedi budget s aktualnim."""
        lines = self._budgets.get(period)
        if not lines:
            return {"ok": False, "error": f"Nema budgeta za {period}"}

        total_budget = sum(l.budget for l in lines)
        total_actual = sum(l.actual for l in lines)
        over_budget = [
            {"konto": l.konto, "naziv": l.naziv,
             "budget": l.budget, "actual": l.actual,
             "variance": round(l.variance, 2),
             "variance_pct": round(l.variance_pct, 1)}
            for l in lines if l.variance > 0
        ]

        return {
            "ok": True,
            "period": period,
            "total_budget": round(total_budget, 2),
            "total_actual": round(total_actual, 2),
            "total_variance": round(total_actual - total_budget, 2),
            "over_budget_items": sorted(
                over_budget, key=lambda x: x["variance"], reverse=True
            ),
            "items_over_budget": len(over_budget),
            "items_total": len(lines),
        }

    # ════════════════════════════════════════
    # COST CENTERS
    # ════════════════════════════════════════

    def add_cost(self, center: str, category: str, amount: float):
        """Dodaj trošak u cost center."""
        if center not in self._cost_centers:
            self._cost_centers[center] = {}
        self._cost_centers[center][category] = (
            self._cost_centers[center].get(category, 0) + amount
        )

    def cost_center_report(self) -> Dict[str, Any]:
        """Izvještaj po cost centrima."""
        report = {}
        for center, cats in self._cost_centers.items():
            total = sum(cats.values())
            report[center] = {
                "categories": dict(sorted(cats.items(),
                                          key=lambda x: x[1], reverse=True)),
                "total": round(total, 2),
            }
        return {
            "centers": report,
            "grand_total": round(sum(
                r["total"] for r in report.values()
            ), 2),
        }

    def get_stats(self):
        return {
            "segments": len(self._segments),
            "budget_periods": len(self._budgets),
            "cost_centers": len(self._cost_centers),
        }


# ════════════════════════════════════════════════════════
# PROŠIRENJA: CVP analiza, break-even, budgeting, variance analysis
# ════════════════════════════════════════════════════════


class CVPAnalysis:
    """Cost-Volume-Profit analiza."""

    @staticmethod
    def break_even(
        fiksni_troskovi: float,
        cijena_po_jed: float,
        varijabilni_po_jed: float,
    ) -> dict:
        """Break-even point analiza."""
        kontribucija = _r2(_d(cijena_po_jed) - _d(varijabilni_po_jed))
        if kontribucija <= 0:
            return {"error": "Kontribucijska marža ≤ 0 — nemoguć break-even"}

        be_kolicina = int(float(_d(fiksni_troskovi) / _d(kontribucija))) + 1
        be_prihod = _r2(_d(be_kolicina) * _d(cijena_po_jed))
        kontribucija_pct = _r2(_d(kontribucija) / _d(cijena_po_jed) * 100)

        return {
            "fiksni_troskovi": _r2(_d(fiksni_troskovi)),
            "cijena_po_jedinici": _r2(_d(cijena_po_jed)),
            "varijabilni_po_jedinici": _r2(_d(varijabilni_po_jed)),
            "kontribucija_po_jedinici": kontribucija,
            "kontribucija_pct": kontribucija_pct,
            "break_even_kolicina": be_kolicina,
            "break_even_prihod": be_prihod,
        }

    @staticmethod
    def what_if_profit(
        fiksni_troskovi: float,
        cijena_po_jed: float,
        varijabilni_po_jed: float,
        ciljana_dobit: float,
    ) -> dict:
        """Koliko jedinica treba prodati za ciljanu dobit?"""
        kontribucija = _d(cijena_po_jed) - _d(varijabilni_po_jed)
        if kontribucija <= 0:
            return {"error": "Kontribucijska marža ≤ 0"}

        potrebna_kolicina = int(float(
            (_d(fiksni_troskovi) + _d(ciljana_dobit)) / kontribucija
        )) + 1
        prihod = _r2(_d(potrebna_kolicina) * _d(cijena_po_jed))

        return {
            "ciljana_dobit": _r2(_d(ciljana_dobit)),
            "potrebna_kolicina": potrebna_kolicina,
            "potrebni_prihod": prihod,
            "ukupni_troskovi": _r2(_d(fiksni_troskovi) + _d(potrebna_kolicina) * _d(varijabilni_po_jed)),
        }


class VarianceAnalysis:
    """Analiza odstupanja — budžet vs. ostvarenje."""

    @staticmethod
    def analyze(budget: dict, actual: dict) -> dict:
        """Usporedi planirane i ostvarene vrijednosti."""
        result = {}
        for key in budget:
            if key in actual and isinstance(budget[key], (int, float)):
                plan = _d(budget[key])
                real = _d(actual[key])
                diff = _r2(real - plan)
                pct = _r2((real - plan) / plan * 100) if plan != 0 else 0
                favorable = diff >= 0 if "prihod" in key.lower() else diff <= 0
                result[key] = {
                    "plan": float(plan),
                    "ostvareno": float(real),
                    "odstupanje": diff,
                    "odstupanje_pct": pct,
                    "ocjena": "✅ povoljno" if favorable else "⚠️ nepovoljno",
                }
        return result
