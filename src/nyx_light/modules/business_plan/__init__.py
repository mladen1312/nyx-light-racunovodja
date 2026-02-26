"""
Modul G4 — Poslovni Planovi

Generiranje strukturiranih poslovnih planova:
  - Financijske projekcije (3-5 godina)
  - Cashflow forecast
  - Scenario analiza (optimistic/base/pessimistic)
  - Loan feasibility (sposobnost otplate kredita)
  - Startup troškovi i ROI kalkulacija
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.business_plan")


@dataclass
class YearProjection:
    """Projekcija za jednu godinu."""
    year: int
    prihodi: float = 0.0
    rashodi: float = 0.0
    dobit_bruto: float = 0.0
    porez: float = 0.0
    dobit_neto: float = 0.0
    cashflow: float = 0.0
    kumulativni_cashflow: float = 0.0


@dataclass
class Scenario:
    """Jedan scenarij (optimistični/bazni/pesimistični)."""
    name: str
    growth_rate: float  # godišnja stopa rasta
    projections: List[YearProjection] = field(default_factory=list)


class BusinessPlanGenerator:
    """Generator poslovnih planova i financijskih projekcija."""

    def __init__(self):
        self._plans_count = 0

    def generate_projections(
        self,
        start_year: int,
        years: int = 5,
        prihodi_y1: float = 100000,
        rashodi_y1: float = 80000,
        growth_prihodi: float = 0.10,
        growth_rashodi: float = 0.05,
        stopa_poreza: float = 0.10,
        investicija: float = 0,
        depreciation_years: int = 5,
    ) -> Dict[str, Any]:
        """Generiraj financijske projekcije."""
        projections = []
        kumul = -investicija

        for i in range(years):
            year = start_year + i
            prihodi = prihodi_y1 * (1 + growth_prihodi) ** i
            rashodi = rashodi_y1 * (1 + growth_rashodi) ** i

            # Amortizacija investicije
            amort = investicija / depreciation_years if i < depreciation_years else 0
            rashodi += amort

            dobit_bruto = prihodi - rashodi
            porez = max(dobit_bruto * stopa_poreza, 0)
            dobit_neto = dobit_bruto - porez
            cashflow = dobit_neto + amort  # dodaj natrag amortizaciju
            kumul += cashflow

            projections.append(YearProjection(
                year=year,
                prihodi=round(prihodi, 2),
                rashodi=round(rashodi, 2),
                dobit_bruto=round(dobit_bruto, 2),
                porez=round(porez, 2),
                dobit_neto=round(dobit_neto, 2),
                cashflow=round(cashflow, 2),
                kumulativni_cashflow=round(kumul, 2),
            ))

        # ROI i payback
        roi = (kumul + investicija) / investicija * 100 if investicija > 0 else 0
        payback = None
        for p in projections:
            if p.kumulativni_cashflow >= 0 and payback is None:
                payback = p.year

        self._plans_count += 1
        return {
            "projections": [self._proj_to_dict(p) for p in projections],
            "summary": {
                "investicija": investicija,
                "total_prihodi": round(sum(p.prihodi for p in projections), 2),
                "total_dobit": round(sum(p.dobit_neto for p in projections), 2),
                "total_cashflow": round(sum(p.cashflow for p in projections), 2),
                "roi_pct": round(roi, 1),
                "payback_year": payback,
                "profitable_from": next(
                    (p.year for p in projections if p.dobit_neto > 0), None
                ),
            },
        }

    def scenario_analysis(
        self,
        start_year: int,
        prihodi_y1: float,
        rashodi_y1: float,
        investicija: float = 0,
        stopa_poreza: float = 0.10,
        years: int = 5,
    ) -> Dict[str, Any]:
        """3 scenarija: optimistični, bazni, pesimistični."""
        scenarios = {
            "optimistični": {"growth_p": 0.15, "growth_r": 0.03},
            "bazni": {"growth_p": 0.08, "growth_r": 0.05},
            "pesimistični": {"growth_p": 0.02, "growth_r": 0.08},
        }

        results = {}
        for name, params in scenarios.items():
            proj = self.generate_projections(
                start_year=start_year,
                years=years,
                prihodi_y1=prihodi_y1,
                rashodi_y1=rashodi_y1,
                growth_prihodi=params["growth_p"],
                growth_rashodi=params["growth_r"],
                stopa_poreza=stopa_poreza,
                investicija=investicija,
            )
            results[name] = proj

        return {"scenarios": results}

    def loan_feasibility(
        self,
        iznos_kredita: float,
        kamatna_stopa: float,
        godine_otplate: int,
        godisnji_cashflow: float,
    ) -> Dict[str, Any]:
        """Provjeri može li se kredit otplatiti iz cashflow-a."""
        # Anuitetni izračun
        r = kamatna_stopa / 100 / 12  # mjesečna stopa
        n = godine_otplate * 12
        if r > 0:
            anuitet = iznos_kredita * r * (1 + r) ** n / ((1 + r) ** n - 1)
        else:
            anuitet = iznos_kredita / n

        godisnji_anuitet = anuitet * 12
        ukupna_kamata = godisnji_anuitet * godine_otplate - iznos_kredita
        dscr = godisnji_cashflow / godisnji_anuitet if godisnji_anuitet > 0 else 0

        feasible = dscr >= 1.25  # Banka traži DSCR >= 1.25

        return {
            "iznos_kredita": iznos_kredita,
            "mjesecni_anuitet": round(anuitet, 2),
            "godisnji_anuitet": round(godisnji_anuitet, 2),
            "ukupna_kamata": round(ukupna_kamata, 2),
            "ukupno_za_platiti": round(iznos_kredita + ukupna_kamata, 2),
            "dscr": round(dscr, 2),
            "feasible": feasible,
            "ocjena": ("✅ Izvedivo — DSCR >= 1.25" if feasible
                       else "❌ Rizično — DSCR < 1.25, banka vjerojatno neće odobriti"),
        }

    def startup_costs(self, items: List[Dict[str, float]]) -> Dict[str, Any]:
        """Kalkulacija startup troškova."""
        total = sum(item.get("iznos", 0) for item in items)
        by_category = {}
        for item in items:
            cat = item.get("kategorija", "Ostalo")
            by_category[cat] = by_category.get(cat, 0) + item.get("iznos", 0)

        return {
            "items": items,
            "by_category": dict(sorted(
                by_category.items(), key=lambda x: x[1], reverse=True
            )),
            "total": round(total, 2),
            "pdv_25": round(total * 0.25, 2),
            "total_s_pdv": round(total * 1.25, 2),
        }

    def _proj_to_dict(self, p: YearProjection) -> Dict[str, Any]:
        return {
            "year": p.year,
            "prihodi": p.prihodi,
            "rashodi": p.rashodi,
            "dobit_bruto": p.dobit_bruto,
            "porez": p.porez,
            "dobit_neto": p.dobit_neto,
            "cashflow": p.cashflow,
            "kumulativni_cashflow": p.kumulativni_cashflow,
        }

    def get_stats(self):
        return {"plans_generated": self._plans_count}
