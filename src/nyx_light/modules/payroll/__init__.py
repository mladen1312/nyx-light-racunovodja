"""
Nyx Light — Modul B: Obračun Plaće (Payroll Engine)

Implementira potpuni bruto→neto obračun za RH prema:
- Zakon o doprinosima
- Zakon o porezu na dohodak
- Pravilnik o porezu na dohodak (neoporezive naknade)

NAPOMENA: Stope i pragovi se ažuriraju u config-u.
Ovaj modul PREDLAŽE obračun — konačno odobrenje je na računovođi.

Stanje propisa: veljača 2026.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.modules.payroll")


# ════════════════════════════════════════════════════════
# Stope i pragovi (ažurirati prema NN izmjenama!)
# Zadnje ažuriranje: veljača 2026.
# ════════════════════════════════════════════════════════

@dataclass
class PayrollRates:
    """Stope doprinosa i poreza — ažurirati pri svakoj zakonskoj izmjeni."""

    # Doprinosi IZ plaće (na teret radnika)
    mio_stup_1_pct: float = 15.0       # MIO I. stup (generacijska solidarnost)
    mio_stup_2_pct: float = 5.0        # MIO II. stup (individualna kapitalizacija)
    # UKUPNO: 20% iz bruto plaće

    # Doprinosi NA plaću (na teret poslodavca)
    zdravstveno_pct: float = 16.5      # Zdravstveno osiguranje
    # Ozljeda na radu i profesionalna bolest: sadržano u zdravstvenom od 2019.

    # Porez na dohodak
    porez_stopa_niza_pct: float = 20.0    # Do praga
    porez_stopa_visa_pct: float = 30.0    # Iznad praga
    porez_prag_godisnji: float = 50_400.00  # EUR godišnje (4.200 EUR mjesečno)
    porez_prag_mjesecni: float = 4_200.00

    # Prirez (ovisi o gradu prebivališta)
    prirez_zagreb_pct: float = 18.0
    prirez_split_pct: float = 15.0
    prirez_rijeka_pct: float = 14.0
    prirez_osijek_pct: float = 13.0

    # Osobni odbitak
    osnovni_osobni_odbitak: float = 560.00   # EUR mjesečno (2026.)
    faktor_uzdrzavani_clan: float = 0.7      # Koeficijent za uzdržavanog člana
    faktor_dijete_1: float = 0.7
    faktor_dijete_2: float = 1.0
    faktor_dijete_3: float = 1.4
    faktor_dijete_4: float = 1.9
    # Svako sljedeće dijete: +0.6 kumulativno

    # Olakšice za mlade
    olaksica_mladi_do_25_pct: float = 100.0  # Potpuno oslobođenje poreza
    olaksica_mladi_25_30_pct: float = 50.0   # 50% oslobođenje poreza

    # Olakšice za invalide
    olaksica_invalid_pct: float = 0.0        # Osobni odbitak faktor
    faktor_invalid_radnik: float = 0.4       # +0.4 na osobni odbitak

    # Neoporezive naknade (Pravilnik o porezu na dohodak)
    naknada_prijevoz_max: float = 0.18       # EUR/km ili mjesečna karta
    naknada_topli_obrok_max: float = 7.96    # EUR/dan (2026.)
    naknada_dnevnica_rh: float = 26.55       # EUR (puni radni dan, >12h)
    naknada_dnevnica_pola: float = 13.28     # EUR (8-12h)
    dar_dijete_max: float = 133.00           # EUR godišnje
    regres_max: float = 331.81               # EUR godišnje

    # Minimalna plaća
    minimalna_bruto: float = 970.00          # EUR (2026.)


@dataclass
class Employee:
    """Podaci o zaposleniku za obračun."""
    name: str
    oib: str = ""
    birth_date: Optional[date] = None
    city: str = "Zagreb"                   # Za prirez
    uzdrzavani_clanovi: int = 0
    djeca: int = 0
    invalid: bool = False
    hrvi: bool = False
    mio_stup_2: bool = True                # Ima li II. stup
    ugovor_vrsta: str = "neodređeno"       # neodređeno, određeno, nepuno
    radno_vrijeme_pct: float = 100.0       # Postotak punog radnog vremena
    bruto_placa: float = 0.0
    sati_rada: int = 176                   # Mjesečni fond sati
    bolovanje_dana: int = 0
    godisnji_dana: int = 0


@dataclass
class PayrollResult:
    """Rezultat obračuna plaće."""
    employee_name: str
    bruto_placa: float = 0.0

    # Doprinosi iz plaće
    mio_stup_1: float = 0.0
    mio_stup_2: float = 0.0
    ukupno_doprinosi_iz: float = 0.0

    # Dohodak
    dohodak: float = 0.0
    osobni_odbitak: float = 0.0
    porezna_osnovica: float = 0.0

    # Porez i prirez
    porez: float = 0.0
    prirez: float = 0.0
    ukupno_porez_prirez: float = 0.0

    # Olakšica za mlade
    olaksica_mladi_pct: float = 0.0
    olaksica_iznos: float = 0.0

    # Neto
    neto_placa: float = 0.0

    # Doprinosi na plaću (teret poslodavca)
    zdravstveno: float = 0.0
    ukupni_trosak_poslodavca: float = 0.0

    # Meta
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    requires_approval: bool = True


class PayrollEngine:
    """
    Obračun plaće za RH.
    
    VAŽNO: Ovaj modul PREDLAŽE obračun.
    Konačno odobrenje i JOPPD predaja su na računovođi.
    """

    def __init__(self, rates: Optional[PayrollRates] = None):
        self.rates = rates or PayrollRates()
        self._calc_count = 0
        logger.info("PayrollEngine inicijaliziran (stope: veljača 2026.)")

    def calculate(self, employee: Employee) -> PayrollResult:
        """Izračunaj plaću za zaposlenika."""
        r = self.rates
        result = PayrollResult(
            employee_name=employee.name,
            bruto_placa=employee.bruto_placa,
        )

        bruto = employee.bruto_placa

        # ── Validacija ──
        min_placa = r.minimalna_bruto * (employee.radno_vrijeme_pct / 100.0)
        if bruto < min_placa:
            result.warnings.append(
                f"⚠️ Bruto plaća ({bruto:.2f} EUR) ispod minimalne ({min_placa:.2f} EUR)!"
            )

        # ── 1. Doprinosi IZ plaće (teret radnika) ──
        result.mio_stup_1 = round(bruto * r.mio_stup_1_pct / 100, 2)
        if employee.mio_stup_2:
            result.mio_stup_2 = round(bruto * r.mio_stup_2_pct / 100, 2)
        else:
            # Stariji radnici bez II. stupa → sav MIO ide u I. stup
            result.mio_stup_1 = round(bruto * (r.mio_stup_1_pct + r.mio_stup_2_pct) / 100, 2)
            result.mio_stup_2 = 0.0
            result.notes.append("Radnik nema II. mirovinski stup — ukupno 20% ide u I. stup")

        result.ukupno_doprinosi_iz = round(result.mio_stup_1 + result.mio_stup_2, 2)

        # ── 2. Dohodak ──
        result.dohodak = round(bruto - result.ukupno_doprinosi_iz, 2)

        # ── 3. Osobni odbitak ──
        odbitak = r.osnovni_osobni_odbitak

        # Uzdržavani članovi
        odbitak += employee.uzdrzavani_clanovi * r.faktor_uzdrzavani_clan * r.osnovni_osobni_odbitak

        # Djeca (progresivni faktori)
        djeca_faktori = [r.faktor_dijete_1, r.faktor_dijete_2, r.faktor_dijete_3, r.faktor_dijete_4]
        for i in range(employee.djeca):
            if i < len(djeca_faktori):
                odbitak += djeca_faktori[i] * r.osnovni_osobni_odbitak
            else:
                odbitak += (djeca_faktori[-1] + 0.6 * (i - len(djeca_faktori) + 1)) * r.osnovni_osobni_odbitak

        # Invaliditet
        if employee.invalid:
            odbitak += r.faktor_invalid_radnik * r.osnovni_osobni_odbitak

        result.osobni_odbitak = round(odbitak, 2)

        # ── 4. Porezna osnovica ──
        result.porezna_osnovica = max(0, round(result.dohodak - result.osobni_odbitak, 2))

        # ── 5. Porez na dohodak (progresivne stope) ──
        if result.porezna_osnovica <= r.porez_prag_mjesecni:
            result.porez = round(result.porezna_osnovica * r.porez_stopa_niza_pct / 100, 2)
        else:
            porez_nizi = round(r.porez_prag_mjesecni * r.porez_stopa_niza_pct / 100, 2)
            porez_visi = round(
                (result.porezna_osnovica - r.porez_prag_mjesecni) * r.porez_stopa_visa_pct / 100, 2
            )
            result.porez = round(porez_nizi + porez_visi, 2)

        # ── 6. Prirez ──
        prirez_pct = self._get_prirez(employee.city)
        result.prirez = round(result.porez * prirez_pct / 100, 2)

        result.ukupno_porez_prirez = round(result.porez + result.prirez, 2)

        # ── 7. Olakšica za mlade ──
        if employee.birth_date:
            age = self._calculate_age(employee.birth_date)
            if age < 25:
                result.olaksica_mladi_pct = r.olaksica_mladi_do_25_pct
                result.olaksica_iznos = result.ukupno_porez_prirez  # 100% oslobođenje
                result.ukupno_porez_prirez = 0.0
                result.notes.append(f"Olakšica za mlade do 25 (dob: {age}) — 100% oslobođenje poreza")
            elif age < 30:
                result.olaksica_mladi_pct = r.olaksica_mladi_25_30_pct
                result.olaksica_iznos = round(result.ukupno_porez_prirez * 0.5, 2)
                result.ukupno_porez_prirez = round(result.ukupno_porez_prirez * 0.5, 2)
                result.notes.append(f"Olakšica za mlade 25-30 (dob: {age}) — 50% oslobođenje poreza")

        # ── 8. Neto plaća ──
        result.neto_placa = round(
            bruto - result.ukupno_doprinosi_iz - result.ukupno_porez_prirez, 2
        )

        # ── 9. Doprinosi NA plaću (teret poslodavca) ──
        result.zdravstveno = round(bruto * r.zdravstveno_pct / 100, 2)

        # ── 10. Ukupni trošak poslodavca ──
        result.ukupni_trosak_poslodavca = round(bruto + result.zdravstveno, 2)

        result.requires_approval = True
        self._calc_count += 1

        return result

    def calculate_ugovor_o_djelu(
        self,
        bruto_naknada: float,
        oib_isplatitelja: str = "",
        oib_primatelja: str = "",
    ) -> Dict[str, Any]:
        """Obračun ugovora o djelu (drugi dohodak)."""
        r = self.rates

        # Doprinosi iz naknade
        mio_1 = round(bruto_naknada * 7.5 / 100, 2)    # 7.5% MIO I
        mio_2 = round(bruto_naknada * 2.5 / 100, 2)    # 2.5% MIO II
        zdravstveno = round(bruto_naknada * 7.5 / 100, 2)  # 7.5% zdravstveno

        dohodak = round(bruto_naknada - mio_1 - mio_2 - zdravstveno, 2)
        porez = round(dohodak * 20 / 100, 2)  # 20% fiksna stopa

        neto = round(bruto_naknada - mio_1 - mio_2 - zdravstveno - porez, 2)

        return {
            "vrsta": "ugovor_o_djelu",
            "bruto_naknada": bruto_naknada,
            "mio_stup_1": mio_1,
            "mio_stup_2": mio_2,
            "zdravstveno": zdravstveno,
            "dohodak": dohodak,
            "porez": porez,
            "neto": neto,
            "requires_approval": True,
            "napomena": "JOPPD obrazac mora biti predan na dan isplate",
        }

    def calculate_autorski_honorar(
        self,
        bruto_honorar: float,
        postotak_normirani_trosak: float = 30.0,  # 30% za većinu autorskih
    ) -> Dict[str, Any]:
        """Obračun autorskog honorara."""
        normirani_trosak = round(bruto_honorar * postotak_normirani_trosak / 100, 2)
        osnovica = round(bruto_honorar - normirani_trosak, 2)

        mio_1 = round(osnovica * 7.5 / 100, 2)
        mio_2 = round(osnovica * 2.5 / 100, 2)
        zdravstveno = round(osnovica * 7.5 / 100, 2)

        dohodak = round(osnovica - mio_1 - mio_2 - zdravstveno, 2)
        porez = round(dohodak * 20 / 100, 2)

        neto = round(bruto_honorar - mio_1 - mio_2 - zdravstveno - porez, 2)

        return {
            "vrsta": "autorski_honorar",
            "bruto_honorar": bruto_honorar,
            "normirani_trosak_pct": postotak_normirani_trosak,
            "normirani_trosak": normirani_trosak,
            "osnovica_za_doprinose": osnovica,
            "mio_stup_1": mio_1,
            "mio_stup_2": mio_2,
            "zdravstveno": zdravstveno,
            "dohodak": dohodak,
            "porez": porez,
            "neto": neto,
            "requires_approval": True,
        }

    def neoporezive_naknade(self, radnih_dana: int = 22) -> Dict[str, float]:
        """Izračunaj maksimalne neoporezive naknade za mjesec."""
        r = self.rates
        return {
            "topli_obrok_max": round(r.naknada_topli_obrok_max * radnih_dana, 2),
            "topli_obrok_po_danu": r.naknada_topli_obrok_max,
            "prijevoz_km_max": r.naknada_prijevoz_max,
            "dnevnica_rh_puna": r.naknada_dnevnica_rh,
            "dnevnica_rh_pola": r.naknada_dnevnica_pola,
            "dar_dijete_god": r.dar_dijete_max,
            "regres_god": r.regres_max,
            "napomena": "Iznosi prema Pravilniku o porezu na dohodak (2026.)",
        }

    def _get_prirez(self, city: str) -> float:
        """Dohvati stopu prireza za grad."""
        prirez_map = {
            "zagreb": self.rates.prirez_zagreb_pct,
            "split": self.rates.prirez_split_pct,
            "rijeka": self.rates.prirez_rijeka_pct,
            "osijek": self.rates.prirez_osijek_pct,
            # Dodati ostale gradove...
        }
        return prirez_map.get(city.lower(), 0.0)

    def _calculate_age(self, birth_date: date) -> int:
        today = date.today()
        return today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "calculations": self._calc_count,
            "rates_date": "veljača 2026.",
            "minimalna_bruto": self.rates.minimalna_bruto,
        }
