"""
Nyx Light — Modul B+: Bolovanje (Naknada plaće za vrijeme bolovanja)

Vrste bolovanja:
1. Na teret poslodavca: prvih 42 dana (70% osnovice, min 85% min.plaće)
2. Na teret HZZO-a: od 43. dana (70% osnovice, ali HZZO nadoknađuje)
3. Izolacija/karantena: od 1. dana na teret HZZO

Osnovica: prosječna plaća zadnjih 6 mjeseci prije bolovanja

Referenca: Zakon o obveznom zdravstvenom osiguranju (čl. 54.-56.)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.modules.bolovanje")

# Konstante
NAKNADA_PCT_POSLODAVAC = 70.0     # % osnovice za prvih 42 dana
NAKNADA_PCT_HZZO = 70.0           # % osnovice za HZZO bolovanje
NAKNADA_PCT_OZLJEDA_RADA = 100.0  # % za ozljedu na radu
MIN_NAKNADA_PCT_MIN_PLACE = 85.0  # % minimalne plaće kao donji prag
POSLODAVAC_DANI = 42              # Dana na teret poslodavca
MIN_PLACA_2026 = 970.0            # EUR bruto

# Vrste bolovanja za JOPPD oznake
VRSTE_BOLOVANJA = {
    "bolest": {"oznaka": "01", "opis": "Bolest", "teret": "poslodavac_pa_hzzo"},
    "ozljeda_izvan_rada": {"oznaka": "02", "opis": "Ozljeda izvan rada", "teret": "poslodavac_pa_hzzo"},
    "ozljeda_na_radu": {"oznaka": "03", "opis": "Ozljeda na radu", "teret": "hzzo_od_1_dana", "pct": 100},
    "profesionalna_bolest": {"oznaka": "04", "opis": "Prof. bolest", "teret": "hzzo_od_1_dana", "pct": 100},
    "njega_clana": {"oznaka": "05", "opis": "Njega člana obitelji", "teret": "hzzo_od_1_dana"},
    "komplikacije_trudnoce": {"oznaka": "06", "opis": "Komplikacije trudnoće", "teret": "hzzo_od_1_dana"},
    "izolacija": {"oznaka": "07", "opis": "Izolacija/karantena", "teret": "hzzo_od_1_dana"},
    "lijecenje_u_inozemstvu": {"oznaka": "08", "opis": "Liječenje u inozemstvu", "teret": "hzzo_od_1_dana"},
}


@dataclass
class BolovanjeResult:
    """Rezultat obračuna bolovanja."""
    djelatnik: str = ""
    vrsta: str = "bolest"
    dani_ukupno: int = 0
    dani_poslodavac: int = 0
    dani_hzzo: int = 0
    
    prosjecna_placa_6mj: float = 0.0
    dnevna_osnovica: float = 0.0
    
    naknada_pct: float = 70.0
    naknada_dnevna: float = 0.0
    naknada_ukupno: float = 0.0
    naknada_teret_poslodavac: float = 0.0
    naknada_teret_hzzo: float = 0.0
    
    min_naknada_dnevna: float = 0.0
    korigirana: bool = False     # True ako je naknada podignuta na minimum
    
    doprinosi_iz: float = 0.0   # MIO I + MIO II
    doprinosi_na: float = 0.0   # Zdravstveno
    
    warnings: List[str] = field(default_factory=list)
    requires_approval: bool = True


class BolovanjeEngine:
    """Obračun naknada za bolovanje."""

    def __init__(self):
        self._count = 0

    def calculate(
        self,
        djelatnik: str,
        vrsta: str,
        dani: int,
        prosjecna_placa_6mj: float,
        sati_dnevno: float = 8.0,
    ) -> BolovanjeResult:
        """Izračunaj naknadu za bolovanje."""
        result = BolovanjeResult(
            djelatnik=djelatnik, vrsta=vrsta, dani_ukupno=dani,
            prosjecna_placa_6mj=prosjecna_placa_6mj,
        )

        vrsta_info = VRSTE_BOLOVANJA.get(vrsta, VRSTE_BOLOVANJA["bolest"])
        teret = vrsta_info["teret"]
        naknada_pct = vrsta_info.get("pct", NAKNADA_PCT_POSLODAVAC)
        result.naknada_pct = naknada_pct

        # Dnevna osnovica (prosječna mjesečna / prosječni radni dani)
        radni_dani_mjesecno = 21.67  # Prosjek
        result.dnevna_osnovica = round(prosjecna_placa_6mj / radni_dani_mjesecno, 2)

        # Dnevna naknada
        result.naknada_dnevna = round(result.dnevna_osnovica * naknada_pct / 100, 2)

        # Minimum: 85% minimalne dnevne plaće
        min_dnevna_placa = round(MIN_PLACA_2026 / radni_dani_mjesecno, 2)
        result.min_naknada_dnevna = round(min_dnevna_placa * MIN_NAKNADA_PCT_MIN_PLACE / 100, 2)

        if result.naknada_dnevna < result.min_naknada_dnevna:
            result.naknada_dnevna = result.min_naknada_dnevna
            result.korigirana = True
            result.warnings.append(
                f"⚠️ Naknada podignuta na minimum (85% min.plaće = {result.min_naknada_dnevna:.2f} EUR/dan)"
            )

        # Raspodjela dana: poslodavac vs HZZO
        if teret == "hzzo_od_1_dana":
            result.dani_poslodavac = 0
            result.dani_hzzo = dani
        else:
            result.dani_poslodavac = min(dani, POSLODAVAC_DANI)
            result.dani_hzzo = max(0, dani - POSLODAVAC_DANI)

        # Iznosi
        result.naknada_teret_poslodavac = round(
            result.naknada_dnevna * result.dani_poslodavac, 2
        )
        result.naknada_teret_hzzo = round(
            result.naknada_dnevna * result.dani_hzzo, 2
        )
        result.naknada_ukupno = round(
            result.naknada_teret_poslodavac + result.naknada_teret_hzzo, 2
        )

        # Doprinosi na naknadu bolovanja
        result.doprinosi_iz = round(result.naknada_ukupno * 0.20, 2)   # 15% + 5%
        result.doprinosi_na = round(result.naknada_ukupno * 0.165, 2)  # 16.5%

        # Upozorenja
        if dani > 42 and teret == "poslodavac_pa_hzzo":
            result.warnings.append(
                f"⚠️ Bolovanje >42 dana — od {POSLODAVAC_DANI + 1}. dana teret HZZO-a. "
                "Potrebna doznaka HZZO-a."
            )

        if vrsta in ("ozljeda_na_radu", "profesionalna_bolest"):
            result.warnings.append(
                "ℹ️ Ozljeda na radu / prof. bolest — 100% naknade od 1. dana na teret HZZO"
            )

        self._count += 1
        return result

    def booking_lines(self, result: BolovanjeResult) -> List[Dict]:
        """Generiraj stavke knjiženja za bolovanje."""
        lines = []

        if result.naknada_teret_poslodavac > 0:
            lines.append({
                "konto": "5200", "strana": "duguje",
                "iznos": result.naknada_teret_poslodavac,
                "opis": f"Bolovanje (teret poslodavca): {result.djelatnik} — {result.dani_poslodavac} dana",
            })

        if result.naknada_teret_hzzo > 0:
            lines.append({
                "konto": "1250", "strana": "duguje",
                "iznos": result.naknada_teret_hzzo,
                "opis": f"Potraživanje HZZO: {result.djelatnik} — {result.dani_hzzo} dana",
            })

        total = result.naknada_ukupno
        if total > 0:
            lines.append({
                "konto": "4200", "strana": "potrazuje",
                "iznos": total,
                "opis": f"Obveza za naknadu bolovanja: {result.djelatnik}",
            })

        return lines

    def get_stats(self):
        return {"bolovanja_calculated": self._count}
