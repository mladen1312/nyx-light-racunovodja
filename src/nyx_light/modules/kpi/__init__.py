"""
Nyx Light — Modul G: KPI Dashboard (Upravljačko računovodstvo)

Izračun ključnih financijskih pokazatelja za klijente:
- Likvidnost (koeficijenti tekuće i ubrzane likvidnosti)
- Profitabilnost (ROA, ROE, profitna marža)
- Zaduženost (koeficijent zaduženosti, pokriće kamata)
- Aktivnost (koeficijent obrtaja)
- Cashflow indikatori

Podaci se izvlače iz bilance (BIL) i RDG-a klijenta.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("nyx_light.modules.kpi")


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
class FinancialData:
    """Financijski podaci iz bilance i RDG-a."""
    # Bilanca — Aktiva
    kratkotrajna_imovina: float = 0.0
    zalihe: float = 0.0
    novac_i_ekvivalenti: float = 0.0
    potraživanja: float = 0.0
    ukupna_aktiva: float = 0.0

    # Bilanca — Pasiva
    kratkorocne_obveze: float = 0.0
    dugorocne_obveze: float = 0.0
    ukupne_obveze: float = 0.0
    kapital: float = 0.0

    # RDG
    prihodi: float = 0.0
    rashodi: float = 0.0
    dobit_prije_oporezivanja: float = 0.0
    neto_dobit: float = 0.0
    troskovi_kamata: float = 0.0
    amortizacija: float = 0.0

    # Dodatno
    broj_zaposlenih: int = 0


class KPIDashboard:
    """Izračun financijskih KPI pokazatelja."""

    def __init__(self):
        self._calc_count = 0

    def calculate_all(self, data: FinancialData) -> Dict[str, Any]:
        """Izračunaj sve KPI pokazatelje."""
        self._calc_count += 1

        return {
            "likvidnost": self._likvidnost(data),
            "profitabilnost": self._profitabilnost(data),
            "zaduzenost": self._zaduzenost(data),
            "aktivnost": self._aktivnost(data),
            "ebitda": self._ebitda(data),
            "po_zaposleniku": self._per_employee(data),
            "ocjena": self._health_score(data),
            "requires_approval": False,  # KPI je informativni
        }

    def _likvidnost(self, d: FinancialData) -> Dict[str, Any]:
        kr_obveze = d.kratkorocne_obveze or 1
        return {
            "tekuca_likvidnost": round(d.kratkotrajna_imovina / kr_obveze, 2),
            "ubrzana_likvidnost": round(
                (d.kratkotrajna_imovina - d.zalihe) / kr_obveze, 2
            ),
            "gotovinska_likvidnost": round(d.novac_i_ekvivalenti / kr_obveze, 2),
            "benchmark": {
                "tekuca": "optimalno 1.5-2.0",
                "ubrzana": "optimalno >1.0",
                "gotovinska": "optimalno >0.2",
            },
        }

    def _profitabilnost(self, d: FinancialData) -> Dict[str, Any]:
        aktiva = d.ukupna_aktiva or 1
        kapital = d.kapital or 1
        prihodi = d.prihodi or 1
        return {
            "roa_pct": round(d.neto_dobit / aktiva * 100, 2),
            "roe_pct": round(d.neto_dobit / kapital * 100, 2),
            "neto_profitna_marza_pct": round(d.neto_dobit / prihodi * 100, 2),
            "bruto_profitna_marza_pct": round(
                d.dobit_prije_oporezivanja / prihodi * 100, 2
            ),
            "benchmark": {
                "roa": "dobro >5%",
                "roe": "dobro >10%",
                "marza": "ovisi o industriji",
            },
        }

    def _zaduzenost(self, d: FinancialData) -> Dict[str, Any]:
        aktiva = d.ukupna_aktiva or 1
        kamata = d.troskovi_kamata or 1
        return {
            "koef_zaduzenosti_pct": round(d.ukupne_obveze / aktiva * 100, 2),
            "omjer_duga_i_kapitala": round(
                d.ukupne_obveze / (d.kapital or 1), 2
            ),
            "pokrice_kamata": round(
                d.dobit_prije_oporezivanja / kamata, 2
            ) if d.troskovi_kamata > 0 else None,
            "benchmark": {
                "zaduzenost": "rizično >60%",
                "dug_kapital": "rizično >2.0",
                "pokrice_kamata": "sigurno >3.0",
            },
        }

    def _aktivnost(self, d: FinancialData) -> Dict[str, Any]:
        aktiva = d.ukupna_aktiva or 1
        potr = d.potraživanja or 1
        return {
            "obrtaj_ukupne_imovine": round(d.prihodi / aktiva, 2),
            "dani_naplate_potrazivanja": round(potr / (d.prihodi / 365), 1)
            if d.prihodi > 0 else None,
            "benchmark": {
                "obrtaj": "viši je bolji",
                "dani_naplate": "optimalno <60 dana",
            },
        }

    def _ebitda(self, d: FinancialData) -> Dict[str, Any]:
        ebitda = d.dobit_prije_oporezivanja + d.troskovi_kamata + d.amortizacija
        prihodi = d.prihodi or 1
        return {
            "ebitda": round(ebitda, 2),
            "ebitda_marza_pct": round(ebitda / prihodi * 100, 2),
        }

    def _per_employee(self, d: FinancialData) -> Optional[Dict[str, Any]]:
        if d.broj_zaposlenih <= 0:
            return None
        n = d.broj_zaposlenih
        return {
            "prihod_po_zaposleniku": round(d.prihodi / n, 2),
            "dobit_po_zaposleniku": round(d.neto_dobit / n, 2),
        }

    def _health_score(self, d: FinancialData) -> Dict[str, Any]:
        """Jednostavna ocjena financijskog zdravlja (1-10)."""
        score = 5.0  # Bazna ocjena

        # Likvidnost
        kr_obveze = d.kratkorocne_obveze or 1
        tekuca = d.kratkotrajna_imovina / kr_obveze
        if tekuca >= 2.0: score += 1.0
        elif tekuca >= 1.5: score += 0.5
        elif tekuca < 1.0: score -= 1.5

        # Profitabilnost
        if d.neto_dobit > 0: score += 1.0
        elif d.neto_dobit < 0: score -= 2.0

        # Zaduženost
        aktiva = d.ukupna_aktiva or 1
        zaduz = d.ukupne_obveze / aktiva
        if zaduz < 0.4: score += 1.0
        elif zaduz > 0.7: score -= 1.5

        # Rast prihoda (ne možemo iz jednog perioda, ali flag)
        if d.prihodi > 0 and d.neto_dobit > 0:
            marza = d.neto_dobit / d.prihodi
            if marza > 0.10: score += 1.0
            elif marza > 0.05: score += 0.5

        score = max(1.0, min(10.0, round(score, 1)))

        if score >= 8:
            status = "Odlično"
        elif score >= 6:
            status = "Dobro"
        elif score >= 4:
            status = "Prosječno"
        else:
            status = "Rizično"

        return {"score": score, "status": status, "max": 10}

    def get_stats(self):
        return {"kpi_calculations": self._calc_count}


# ════════════════════════════════════════════════════════
# PROŠIRENJA: Financijski KPI-evi, trend analiza, benchmarking
# ════════════════════════════════════════════════════════

class FinancijskiKPI:
    """Izračun ključnih financijskih pokazatelja."""

    @staticmethod
    def profitabilnost(
        ukupni_prihodi: float,
        ukupni_rashodi: float,
        neto_dobit: float,
        vlastiti_kapital: float = 0,
        ukupna_imovina: float = 0,
    ) -> dict:
        """Pokazatelji profitabilnosti."""
        prihodi = _d(ukupni_prihodi) if ukupni_prihodi else _d(1)
        return {
            "bruto_marza_pct": _r2((_d(ukupni_prihodi) - _d(ukupni_rashodi)) / prihodi * 100),
            "neto_marza_pct": _r2(_d(neto_dobit) / prihodi * 100),
            "ROE_pct": _r2(_d(neto_dobit) / _d(vlastiti_kapital or 1) * 100),
            "ROA_pct": _r2(_d(neto_dobit) / _d(ukupna_imovina or 1) * 100),
            "EBITDA": _r2(_d(ukupni_prihodi) - _d(ukupni_rashodi)),
        }

    @staticmethod
    def zaduzenost(
        ukupne_obveze: float,
        ukupna_imovina: float,
        vlastiti_kapital: float,
        kratkorocne_obveze: float = 0,
    ) -> dict:
        """Pokazatelji zaduženosti."""
        return {
            "koef_zaduzenosti": _r2(_d(ukupne_obveze) / _d(ukupna_imovina or 1)),
            "koef_financiranja": _r2(_d(ukupne_obveze) / _d(vlastiti_kapital or 1)),
            "koef_pokrica": _r2(_d(vlastiti_kapital) / _d(ukupna_imovina or 1)),
            "preporuke": {
                "zaduzenost": "< 0.5 (idealno)",
                "financiranje": "< 1.0",
                "pokrice": "> 0.5",
            },
        }

    @staticmethod
    def aktivnost(
        prihodi_od_prodaje: float,
        ukupna_imovina: float,
        kratkotrajna_imovina: float,
        potrazivanja: float,
        zalihe: float,
        dani: int = 365,
    ) -> dict:
        """Pokazatelji aktivnosti (obrtaja)."""
        prihodi = _d(prihodi_od_prodaje) if prihodi_od_prodaje else _d(1)
        return {
            "obrtaj_ukupne_imovine": _r2(prihodi / _d(ukupna_imovina or 1)),
            "obrtaj_kratkotrajne": _r2(prihodi / _d(kratkotrajna_imovina or 1)),
            "dani_naplate": int(float(_d(potrazivanja) / (prihodi / _d(dani)))) if float(prihodi) > 0 else 0,
            "dani_zaliha": int(float(_d(zalihe) / (prihodi / _d(dani)))) if float(prihodi) > 0 else 0,
        }

    @staticmethod
    def trend(periodi: list) -> dict:
        """Trend analiza — usporedi više perioda."""
        if len(periodi) < 2:
            return {"error": "Potrebna minimalno 2 perioda za trend"}

        trends = {}
        for key in periodi[0]:
            if key == "period" or not isinstance(periodi[0][key], (int, float)):
                continue
            values = [p.get(key, 0) for p in periodi]
            first = values[0] or 1
            trends[key] = {
                "values": values,
                "promjena_pct": _r2((_d(values[-1]) - _d(values[0])) / _d(first) * 100),
                "trend": "↑" if values[-1] > values[0] else ("↓" if values[-1] < values[0] else "→"),
            }
        return trends
