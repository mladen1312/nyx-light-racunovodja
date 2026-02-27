"""
═══════════════════════════════════════════════════════════════════════════════
SPRINT 16 — RIGOROZNO TESTIRANJE: MATEMATIKA vs AI
═══════════════════════════════════════════════════════════════════════════════

NAČELO: Računovodstveni sustav MORA imati čistu granicu:

  ┌─────────────────────────────────────────────────────────┐
  │  MATEMATIČKA SKRIPTA (determinističko)                  │
  │  • Obračun plaća (bruto→neto)                          │
  │  • PDV izračun (obveza - pretporez)                    │
  │  • Amortizacija (linearna/ubrzana)                     │
  │  • Porez na dobit (PD obrazac)                         │
  │  • Drugi dohodak (autorski/ugovor o djelu)             │
  │  • Blagajna (AML limiti, stanje)                       │
  │  • Putni nalozi (km naknada, dnevnice)                 │
  │  • IOS usklađivanja (razlike)                          │
  │  → NIKAD ne ovisi o LLM-u                             │
  │  → UVIJEK daje identičan rezultat za isti ulaz         │
  │  → 0% šanse za halucinaciju                            │
  └─────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────┐
  │  AI ASISTENCIJA (LLM-ovisno)                           │
  │  • Prijedlog konta (kontiranje)                        │
  │  • Tumačenje zakona (RAG + LLM)                        │
  │  • Klasifikacija dokumenata                            │
  │  • Chat odgovori na porezna pitanja                    │
  │  → UVIJEK označeno confidence + requires_approval      │
  │  → NIKAD ne ulazi u ERP bez ljudskog klika             │
  │  → Svaki AI output ima metadata o izvoru               │
  └─────────────────────────────────────────────────────────┘

Test pokriva:
  A) MATEMATIKA — 100% determinističko, ručno verificirano
  B) AI GRANICE — provjera da AI nikad ne zaobilazi odobrenje
  C) ANTI-HALUCINACIJA — provjera da matematika ne ovisi o LLM-u
  D) OVERSEER — sigurnosne tvrde granice
  E) SILICON — Apple Silicon optimizacijski sloj
  F) KNOWLEDGE VAULT — čuvanje znanja pri zamjeni modela

Autor: Nyx Light Sprint 16
Datum: veljača 2026.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import json
import math
import hashlib
from datetime import date, datetime
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

import pytest

# Dodaj src u path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ═══════════════════════════════════════════════════════════════════
# SECTION A: MATEMATIČKI TESTOVI — 100% DETERMINISTIČKI
# Svaki test ručno izračunat. Nijedan ne koristi LLM.
# ═══════════════════════════════════════════════════════════════════

class TestPayrollMath:
    """
    Obračun plaće — čista matematika.
    
    Formula (2026. RH):
      1. MIO I = bruto × 15%
      2. MIO II = bruto × 5%
      3. Dohodak = bruto - MIO I - MIO II
      4. Osobni odbitak = 560 + faktori(djeca, uzdržavani)
      5. Porezna osnovica = max(0, dohodak - osobni_odbitak)
      6. Porez = 20% do 4.200 EUR + 30% iznad
      7. Prirez = porez × stopa_grada
      8. Neto = bruto - MIO - porez - prirez
      9. Zdravstveno (poslodavac) = bruto × 16.5%
    """

    def setup_method(self):
        from nyx_light.modules.payroll import PayrollEngine, PayrollRates, Employee
        self.engine = PayrollEngine()
        self.Employee = Employee

    # ── A1: Prosječna plaća Zagreb, bez djece ──
    def test_standard_payroll_zagreb_no_children(self):
        """Bruto 2.000 EUR, Zagreb, bez djece — ručni izračun."""
        emp = self.Employee(
            name="Ana Horvat", bruto_placa=2000.0,
            city="Zagreb", djeca=0, uzdrzavani_clanovi=0,
        )
        r = self.engine.calculate(emp)

        # MIO iz plaće
        assert r.mio_stup_1 == 300.00   # 2000 × 15%
        assert r.mio_stup_2 == 100.00   # 2000 × 5%
        assert r.ukupno_doprinosi_iz == 400.00

        # Dohodak
        assert r.dohodak == 1600.00  # 2000 - 400

        # Osobni odbitak = 560 (samo osnovni)
        assert r.osobni_odbitak == 560.00

        # Porezna osnovica = 1600 - 560 = 1040
        assert r.porezna_osnovica == 1040.00

        # Porez = 1040 × 20% = 208 (ispod praga 4200)
        assert r.porez == 208.00

        # Prirez Zagreb 18% = 208 × 0.18 = 37.44
        assert r.prirez == 37.44

        # Ukupno porez + prirez
        assert r.ukupno_porez_prirez == 245.44

        # Neto = 2000 - 400 - 245.44 = 1354.56
        assert r.neto_placa == 1354.56

        # Zdravstveno (poslodavac) = 2000 × 16.5% = 330
        assert r.zdravstveno == 330.00

        # Ukupni trošak = 2000 + 330 = 2330
        assert r.ukupni_trosak_poslodavca == 2330.00

    # ── A2: Visoka plaća — progresivni porez ──
    def test_high_salary_progressive_tax(self):
        """Bruto 6.000 EUR — porezna osnovica prelazi prag 4.200."""
        emp = self.Employee(
            name="Marko Kovačić", bruto_placa=6000.0,
            city="Zagreb", djeca=0, uzdrzavani_clanovi=0,
        )
        r = self.engine.calculate(emp)

        # MIO
        assert r.mio_stup_1 == 900.00  # 6000 × 15%
        assert r.mio_stup_2 == 300.00  # 6000 × 5%

        # Dohodak = 6000 - 1200 = 4800
        assert r.dohodak == 4800.00

        # Osobni odbitak = 560
        # Porezna osnovica = 4800 - 560 = 4240
        assert r.porezna_osnovica == 4240.00

        # Porez: 4200 × 20% + (4240 - 4200) × 30% = 840 + 12 = 852
        assert r.porez == 852.00

        # Prirez: 852 × 18% = 153.36
        assert r.prirez == 153.36

    # ── A3: Plaća s djecom — osobni odbitak ──
    def test_salary_with_children(self):
        """Bruto 2.500 EUR, Zagreb, 2 djece."""
        emp = self.Employee(
            name="Ivana Babić", bruto_placa=2500.0,
            city="Zagreb", djeca=2, uzdrzavani_clanovi=0,
        )
        r = self.engine.calculate(emp)

        # Osobni odbitak:
        # Osnovni = 560
        # Dijete 1: 0.7 × 560 = 392
        # Dijete 2: 1.0 × 560 = 560
        # Ukupno: 560 + 392 + 560 = 1512
        assert r.osobni_odbitak == 1512.00

        # Dohodak = 2500 - 500 = 2000
        assert r.dohodak == 2000.00

        # Porezna osnovica = 2000 - 1512 = 488
        assert r.porezna_osnovica == 488.00

        # Porez = 488 × 20% = 97.60
        assert r.porez == 97.60

    # ── A4: Plaća s 3 djece + uzdržavani član ──
    def test_salary_3children_dependent(self):
        """Bruto 3.000 EUR, Split, 3 djece + 1 uzdržavani."""
        emp = self.Employee(
            name="Pero Perić", bruto_placa=3000.0,
            city="Split", djeca=3, uzdrzavani_clanovi=1,
        )
        r = self.engine.calculate(emp)

        # Osobni odbitak:
        # Osnovni = 560
        # Uzdržavani: 1 × 0.7 × 560 = 392
        # Dijete 1: 0.7 × 560 = 392
        # Dijete 2: 1.0 × 560 = 560
        # Dijete 3: 1.4 × 560 = 784
        # Ukupno: 560 + 392 + 392 + 560 + 784 = 2688
        assert r.osobni_odbitak == 2688.00

        # Dohodak = 3000 - 600 = 2400
        # Porezna osnovica = max(0, 2400 - 2688) = 0
        assert r.porezna_osnovica == 0.00

        # Neto = 3000 - 600 - 0 = 2400
        assert r.neto_placa == 2400.00

        # Prirez Split 15%
        assert r.prirez == 0.00  # porez je 0

    # ── A5: Minimalna plaća ──
    def test_minimum_wage_check(self):
        """Plaća ispod minimalne (970 EUR) treba upozorenje."""
        emp = self.Employee(
            name="Test Worker", bruto_placa=800.0, city="Zagreb",
        )
        r = self.engine.calculate(emp)
        assert any("ispod minimalne" in w for w in r.warnings)

    # ── A6: Bez II. stupa ──
    def test_no_second_pillar(self):
        """Radnik bez II. mirovinskog stupa — sav MIO u I. stup."""
        emp = self.Employee(
            name="Stariji radnik", bruto_placa=2000.0,
            city="Zagreb", mio_stup_2=False,
        )
        r = self.engine.calculate(emp)

        # Svih 20% ide u I. stup
        assert r.mio_stup_1 == 400.00  # 2000 × 20%
        assert r.mio_stup_2 == 0.00
        assert r.ukupno_doprinosi_iz == 400.00

    # ── A7: Neto provjera invarijante ──
    def test_payroll_invariant(self):
        """bruto = neto + doprinosi_iz + porez + prirez (za svaku plaću)."""
        for bruto in [970, 1500, 2000, 3000, 5000, 8000, 15000]:
            emp = self.Employee(
                name="Test", bruto_placa=float(bruto), city="Zagreb",
            )
            r = self.engine.calculate(emp)

            # FUNDAMENTALNA INVARIJANTA:
            reconstructed = r.neto_placa + r.ukupno_doprinosi_iz + r.ukupno_porez_prirez
            assert abs(reconstructed - r.bruto_placa) < 0.01, (
                f"HALUCINACIJA! Bruto {bruto}: neto({r.neto_placa}) + "
                f"doprinosi({r.ukupno_doprinosi_iz}) + porez({r.ukupno_porez_prirez}) "
                f"= {reconstructed} ≠ {r.bruto_placa}"
            )

    # ── A8: Determinizam — isti ulaz = isti izlaz UVIJEK ──
    def test_payroll_deterministic(self):
        """Isti parametri MORAJU dati identičan rezultat 100 puta."""
        emp = self.Employee(
            name="Determinizam Test", bruto_placa=2500.0,
            city="Zagreb", djeca=1, uzdrzavani_clanovi=1,
        )

        results = []
        for _ in range(100):
            r = self.engine.calculate(emp)
            results.append(r.neto_placa)

        # SVA 100 izračuna MORAJU biti identična
        assert len(set(results)) == 1, (
            f"HALUCINACIJA! Payroll nije deterministički — "
            f"dobiveno {len(set(results))} različitih rezultata za isti ulaz!"
        )


class TestPDVMath:
    """
    PDV prijava — čista matematika.
    
    Stope: 25%, 13%, 5%, 0%
    Obveza = Σ izlazni PDV
    Pretporez = Σ ulazni PDV  
    Za uplatu = obveza - pretporez (ako > 0)
    Za povrat = pretporez - obveza (ako > 0)
    """

    def setup_method(self):
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
        self.engine = PDVPrijavaEngine()
        self.PDVStavka = PDVStavka

    def test_basic_pdv_calculation(self):
        """Osnovni PDV izračun — 3 izlazna, 2 ulazna računa."""
        stavke = [
            # Izlazni (obveza)
            self.PDVStavka(tip="izlazni", osnovica=10000.0, pdv_stopa=25, pdv_iznos=2500.0),
            self.PDVStavka(tip="izlazni", osnovica=5000.0, pdv_stopa=13, pdv_iznos=650.0),
            self.PDVStavka(tip="izlazni", osnovica=2000.0, pdv_stopa=5, pdv_iznos=100.0),
            # Ulazni (pretporez)
            self.PDVStavka(tip="ulazni", osnovica=8000.0, pdv_stopa=25, pdv_iznos=2000.0),
            self.PDVStavka(tip="ulazni", osnovica=3000.0, pdv_stopa=13, pdv_iznos=390.0),
        ]

        ppo = self.engine.calculate(stavke, period="2026-02")

        # Izlazni
        assert ppo.izlazni_25_pdv == 2500.0
        assert ppo.izlazni_13_pdv == 650.0
        assert ppo.izlazni_5_pdv == 100.0

        # Pretporez
        assert ppo.pretporez_25 == 2000.0
        assert ppo.pretporez_13 == 390.0

        # Obveza = 2500 + 650 + 100 = 3250
        assert ppo.ukupna_obveza == 3250.0

        # Pretporez = 2000 + 390 = 2390
        assert ppo.ukupni_pretporez == 2390.0

        # Za uplatu = 3250 - 2390 = 860
        assert ppo.za_uplatu == 860.0
        assert ppo.za_povrat == 0.0

    def test_pdv_refund(self):
        """Pretporez > obveza → povrat PDV-a."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=5000.0, pdv_stopa=25, pdv_iznos=1250.0),
            self.PDVStavka(tip="ulazni", osnovica=20000.0, pdv_stopa=25, pdv_iznos=5000.0),
        ]

        ppo = self.engine.calculate(stavke, period="2026-01")
        assert ppo.za_uplatu == 0.0
        assert ppo.za_povrat == 3750.0  # 5000 - 1250

    def test_pdv_invariant(self):
        """za_uplatu ili za_povrat = |obveza - pretporez|."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=7777.0, pdv_stopa=25, pdv_iznos=1944.25),
            self.PDVStavka(tip="ulazni", osnovica=3333.0, pdv_stopa=25, pdv_iznos=833.25),
        ]
        ppo = self.engine.calculate(stavke)

        razlika = round(ppo.ukupna_obveza - ppo.ukupni_pretporez, 2)
        if razlika > 0:
            assert ppo.za_uplatu == razlika
            assert ppo.za_povrat == 0
        else:
            assert ppo.za_povrat == abs(razlika)
            assert ppo.za_uplatu == 0

    def test_pdv_eu_reverse_charge(self):
        """EU reverse charge — ne ulazi u obvezu, ide na EC Sales List."""
        stavke = [
            self.PDVStavka(
                tip="izlazni", osnovica=15000.0, pdv_stopa=0,
                pdv_iznos=0.0, eu_transakcija=True, reverse_charge=True,
            ),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.eu_isporuke_osnovica == 15000.0
        assert ppo.ukupna_obveza == 0.0  # Reverse charge ne daje obvezu

    def test_pdv_deterministic(self):
        """PDV izračun mora biti 100% determinističan."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=12345.67, pdv_stopa=25, pdv_iznos=3086.42),
            self.PDVStavka(tip="ulazni", osnovica=9876.54, pdv_stopa=25, pdv_iznos=2469.14),
        ]
        results = set()
        for _ in range(50):
            ppo = self.engine.calculate(stavke, period="2026-02")
            results.add(ppo.za_uplatu)
        assert len(results) == 1, "PDV izračun nije deterministički!"


class TestDepreciationMath:
    """
    Amortizacija — čista matematika.
    
    Linearna: mjesečno = nabavna × godišnja_stopa / 100 / 12
    Prag za dugotrajnu imovinu: 665 EUR
    """

    def setup_method(self):
        from nyx_light.modules.osnovna_sredstva import (
            OsnovnaSredstvaEngine, PRAG_DUGOTRAJNA_IMOVINA,
            AMORTIZACIJSKE_STOPE,
        )
        self.engine = OsnovnaSredstvaEngine()
        self.PRAG = PRAG_DUGOTRAJNA_IMOVINA
        self.STOPE = AMORTIZACIJSKE_STOPE

    def test_small_inventory_threshold(self):
        """Ispod 665 EUR = sitan inventar, jednokratni otpis."""
        result = self.engine.add_asset({
            "naziv": "USB hub",
            "nabavna_vrijednost": 50.0,
            "vrsta": "računalna_oprema",
        })
        assert result["status"] == "sitan_inventar"
        assert result["jednokratni_otpis"] is True

    def test_threshold_boundary(self):
        """Točno 665 EUR = dugotrajna imovina."""
        result = self.engine.add_asset({
            "naziv": "Printer",
            "nabavna_vrijednost": 665.0,
            "vrsta": "uredska_oprema",
        })
        assert result.get("status") != "sitan_inventar"

    def test_computer_depreciation(self):
        """Računalo 2.000 EUR, stopa 50%, vijek 2 godine."""
        self.engine.add_asset({
            "naziv": "MacBook Pro",
            "nabavna_vrijednost": 2000.0,
            "vrsta": "računalna_oprema",
        })

        depr = self.engine.calculate_monthly_depreciation()
        assert len(depr) == 1

        # Mjesečna = 2000 × 50% / 12 = 83.33
        assert depr[0]["mjesecna_amortizacija"] == 83.33

    def test_furniture_depreciation(self):
        """Namještaj 5.000 EUR, stopa 20%, vijek 5 godina."""
        self.engine.add_asset({
            "naziv": "Uredski stol",
            "nabavna_vrijednost": 5000.0,
            "vrsta": "namjestaj",
        })
        depr = self.engine.calculate_monthly_depreciation()

        # Mjesečna = 5000 × 20% / 12 = 83.33
        assert depr[0]["mjesecna_amortizacija"] == 83.33

    def test_depreciation_cannot_exceed_cost(self):
        """Ukupna amortizacija ne smije premašiti nabavnu vrijednost."""
        self.engine.add_asset({
            "naziv": "Software licenca",
            "nabavna_vrijednost": 1000.0,
            "vrsta": "software",  # 50% godišnje
        })

        # Primijeni amortizaciju 24 puta (2 godine — puni vijek)
        for _ in range(24):
            depr = self.engine.calculate_monthly_depreciation()
            if depr:
                self.engine.apply_depreciation(depr)

        # Nakon punog vijeka, trebalo bi biti potpuno amortizirano
        depr = self.engine.calculate_monthly_depreciation()
        assert len(depr) == 0, "Potpuno amortizirana sredstva ne smiju generirati troškove!"

    def test_statutory_rates(self):
        """Zakonske stope amortizacije moraju odgovarati Pravilniku."""
        expected = {
            "građevinski_objekti": 5.0,
            "osobni_automobili": 20.0,
            "računalna_oprema": 50.0,
            "uredska_oprema": 25.0,
            "software": 50.0,
        }
        for vrsta, expected_rate in expected.items():
            assert self.STOPE[vrsta]["stopa"] == expected_rate, (
                f"Stopa za {vrsta} treba biti {expected_rate}%!"
            )


class TestCorporateTaxMath:
    """
    Porez na dobit — čista matematika.
    
    Stope (2026.):
      ≤ 1.000.000 EUR prihoda → 10%
      > 1.000.000 EUR prihoda → 18%
    
    Porezna osnovica = dobit + uvećanja - umanjenja
    """

    def setup_method(self):
        from nyx_light.modules.porez_dobit import PorezDobitiEngine
        self.engine = PorezDobitiEngine()

    def test_small_company_tax(self):
        """Tvrtka s prihodom 500.000 EUR → stopa 10%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=500_000.0,
            ukupni_rashodi=400_000.0,
        )
        # Dobit = 100.000
        assert pd.dobit_prije_oporezivanja == 100_000.00
        # Stopa 10% (prihod < 1M)
        assert pd.stopa == 10.0
        # Porez = 100.000 × 10% = 10.000
        assert pd.porez_na_dobit == 10_000.00

    def test_large_company_tax(self):
        """Tvrtka s prihodom 2.000.000 EUR → stopa 18%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=2_000_000.0,
            ukupni_rashodi=1_500_000.0,
        )
        assert pd.stopa == 18.0
        assert pd.porez_na_dobit == 90_000.00  # 500.000 × 18%

    def test_tax_with_adjustments(self):
        """Porez s uvećanjima i umanjenjima."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=800_000.0,
            ukupni_rashodi=700_000.0,
            uvecanja={"reprezentacija_50pct": 5000.0, "kazne": 2000.0},
            umanjenja={"dividende": 3000.0},
        )
        # Dobit = 100.000
        # Uvećanja = 5000 + 2000 = 7000
        # Umanjenja = 3000
        # Porezna osnovica = 100.000 + 7000 - 3000 = 104.000
        assert pd.porezna_osnovica == 104_000.00
        # 10% (prihod < 1M)
        assert pd.porez_na_dobit == 10_400.00

    def test_loss_no_tax(self):
        """Gubitak → porezna osnovica = 0, porez = 0."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=300_000.0,
            ukupni_rashodi=350_000.0,
        )
        assert pd.dobit_prije_oporezivanja == -50_000.00
        assert pd.porezna_osnovica == 0.0
        assert pd.porez_na_dobit == 0.0

    def test_threshold_boundary(self):
        """Prihod točno 1.000.000 EUR → još uvijek 10%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=1_000_000.0,
            ukupni_rashodi=900_000.0,
        )
        assert pd.stopa == 10.0

    def test_threshold_above(self):
        """Prihod 1.000.001 EUR → prelazi na 18%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=1_000_001.0,
            ukupni_rashodi=900_000.0,
        )
        assert pd.stopa == 18.0


class TestDrugiDohodakMath:
    """
    Drugi dohodak (autorski honorar, ugovor o djelu) — čista matematika.
    """

    def setup_method(self):
        from nyx_light.modules.drugi_dohodak import DrugiDohodakEngine
        self.engine = DrugiDohodakEngine()

    def test_ugovor_o_djelu(self):
        """Ugovor o djelu 1.000 EUR, Zagreb."""
        r = self.engine.calculate(
            ime="Test", oib="12345678901",
            bruto=1000.0, vrsta="ugovor_o_djelu", grad="Zagreb",
        )
        # Dohodak = bruto (nema neoporezivog dijela)
        assert r.dohodak == 1000.0

        # MIO I = 1000 × 15% = 150
        assert r.mio_1 == 150.0
        # MIO II = 1000 × 5% = 50
        assert r.mio_2 == 50.0

        # Porezna osnovica = 1000 - 200 = 800
        assert r.porezna_osnovica == 800.0

        # Porez = 800 × 20% = 160
        assert r.porez == 160.0

        # Prirez ZG 18% = 160 × 0.18 = 28.80
        assert r.prirez == 28.80

        # Neto = 1000 - 200 - 160 - 28.80 = 611.20
        assert r.neto == 611.20

    def test_autorski_honorar(self):
        """Autorski honorar 2.000 EUR — 30% neoporezivo."""
        r = self.engine.calculate(
            ime="Autor", oib="12345678901",
            bruto=2000.0, vrsta="autorski_honorar", grad="Zagreb",
        )
        # Neoporezivi dio = 2000 × 30% = 600
        assert r.neoporezivi_dio == 600.0

        # Dohodak = 2000 - 600 = 1400
        assert r.dohodak == 1400.0

        # MIO = 1400 × 20% = 280
        assert r.ukupno_mio == 280.0

        # Porezna osnovica = 1400 - 280 = 1120
        assert r.porezna_osnovica == 1120.0

        # Porez = 1120 × 20% = 224
        assert r.porez == 224.0

    def test_drugi_dohodak_invariant(self):
        """neto = bruto - MIO - porez - prirez (uvijek)."""
        for bruto in [500, 1000, 2000, 5000, 10000]:
            for vrsta in ["ugovor_o_djelu", "autorski_honorar"]:
                r = self.engine.calculate(
                    ime="Inv", oib="11111111111",
                    bruto=float(bruto), vrsta=vrsta, grad="Zagreb",
                )
                expected_neto = round(
                    bruto - r.ukupno_mio - r.ukupno_porez_prirez, 2
                )
                assert abs(r.neto - expected_neto) < 0.01, (
                    f"HALUCINACIJA u drugom dohotku! {vrsta} bruto={bruto}: "
                    f"neto {r.neto} ≠ {expected_neto}"
                )


class TestBlagajnaMath:
    """
    Blagajna — AML provjere, čista matematika.
    """

    def setup_method(self):
        from nyx_light.modules.blagajna.validator import BlagajnaValidator, BlagajnaTx
        self.validator = BlagajnaValidator()
        self.BlagajnaTx = BlagajnaTx

    def test_aml_limit(self):
        """Gotovinska transakcija ≥ 10.000 EUR — ZABRANA (AML čl. 30.)."""
        tx = self.BlagajnaTx(iznos=10_000.0)
        r = self.validator.validate_transaction(tx)
        assert any("ZABRANA" in e or "AML" in e for e in r.errors), (
            "AML limit od 10.000 EUR MORA biti provjeravan matematički!"
        )

    def test_aml_below_limit(self):
        """9.999 EUR — prolazi AML provjeru."""
        tx = self.BlagajnaTx(iznos=9_999.99)
        r = self.validator.validate_transaction(tx)
        aml_errors = [e for e in r.errors if "AML" in e or "ZABRANA" in e]
        assert len(aml_errors) == 0


class TestPutniNaloziMath:
    """
    Putni nalozi — km naknada, dnevnice — čista matematika.
    """

    def setup_method(self):
        from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker, PutniNalog
        self.checker = PutniNalogChecker()
        self.PutniNalog = PutniNalog

    def test_km_rate_within_limit(self):
        """200 km × 0.30 EUR = 60 EUR (porezno priznato)."""
        pn = self.PutniNalog(km=200, km_naknada=0.30)
        r = self.checker.validate_full(pn)
        assert r.km_naknada_ukupno == 60.00

    def test_km_rate_above_limit(self):
        """Km naknada iznad 0.30 EUR — upozorenje."""
        pn = self.PutniNalog(km=100, km_naknada=0.50)
        r = self.checker.validate_full(pn)
        assert any("nepriznata" in w.lower() or "porezno" in w.lower() for w in r.warnings)
        # Porezno priznati dio = 100 × 0.30 = 30
        assert r.km_naknada_ukupno == 30.00

    def test_dnevnica_above_max(self):
        """Dnevnica iznad 26.55 EUR — upozorenje."""
        pn = self.PutniNalog(dnevnica=35.0)
        r = self.checker.validate_full(pn)
        assert any("dnevnica" in w.lower() for w in r.warnings)

    def test_statutory_rates(self):
        """Zakonski limiti moraju odgovarati Pravilniku 2026."""
        from nyx_light.modules.putni_nalozi.checker import (
            MAX_KM_RATE, DNEVNICA_PUNA, DNEVNICA_POLA,
            REPREZENTACIJA_NEPRIZNATO_PCT,
        )
        assert MAX_KM_RATE == 0.30
        assert DNEVNICA_PUNA == 26.55
        assert DNEVNICA_POLA == 13.28
        assert REPREZENTACIJA_NEPRIZNATO_PCT == 50.0


# ═══════════════════════════════════════════════════════════════════
# SECTION B: AI GRANICE — requires_approval UVIJEK True
# ═══════════════════════════════════════════════════════════════════

class TestAIBoundaries:
    """
    Svaki AI output MORA imati:
      - requires_approval = True
      - confidence score
      - source oznaku
    
    AI NIKAD ne smije autonomno knjižiti.
    """

    def test_payroll_requires_approval(self):
        """Obračun plaće UVIJEK traži odobrenje."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        engine = PayrollEngine()
        emp = Employee(name="Test", bruto_placa=2000.0, city="Zagreb")
        r = engine.calculate(emp)
        assert r.requires_approval is True, (
            "KRITIČNO: Obračun plaće MORA zahtijevati ljudsko odobrenje!"
        )

    def test_kontiranje_requires_approval(self):
        """AI prijedlog konta UVIJEK traži odobrenje."""
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        engine = KontiranjeEngine()
        result = engine.suggest_konto("Kupnja uredskog materijala")
        assert result["requires_approval"] is True, (
            "KRITIČNO: AI kontiranje MORA zahtijevati ljudsko odobrenje!"
        )

    def test_kontiranje_has_confidence(self):
        """AI kontiranje MORA imati confidence score."""
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        engine = KontiranjeEngine()
        result = engine.suggest_konto("Račun za internet usluge")
        assert "confidence" in result, (
            "AI kontiranje MORA vraćati confidence score!"
        )
        assert 0.0 <= result["confidence"] <= 1.0

    def test_kontiranje_memory_hint_requires_approval(self):
        """Čak i kad L2 memorija daje hint, MORA biti requires_approval."""
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        engine = KontiranjeEngine()
        result = engine.suggest_konto(
            "Trošak usluge",
            memory_hint={"hint": "7200", "confidence": 0.95},
        )
        assert result["requires_approval"] is True
        assert result["source"] == "L2_semantic_memory"

    def test_ugovor_o_djelu_requires_approval(self):
        """Obračun ugovora o djelu traži odobrenje."""
        from nyx_light.modules.payroll import PayrollEngine
        engine = PayrollEngine()
        r = engine.calculate_ugovor_o_djelu(1000.0)
        assert r["requires_approval"] is True

    def test_no_module_auto_books(self):
        """Nijedan modul ne smije imati auto_book ili auto_post metodu."""
        import nyx_light.modules as modules_pkg
        import pkgutil
        import importlib

        for importer, modname, ispkg in pkgutil.walk_packages(
            modules_pkg.__path__, modules_pkg.__name__ + "."
        ):
            try:
                mod = importlib.import_module(modname)
            except Exception:
                continue

            for attr_name in dir(mod):
                attr_name_lower = attr_name.lower()
                assert "auto_book" not in attr_name_lower, (
                    f"KRITIČNO: {modname}.{attr_name} — autonomno knjiženje zabranjeno!"
                )
                assert "auto_post_to_erp" not in attr_name_lower, (
                    f"KRITIČNO: {modname}.{attr_name} — autonomni ERP unos zabranjen!"
                )


# ═══════════════════════════════════════════════════════════════════
# SECTION C: ANTI-HALUCINACIJA — matematika NIKAD ne ovisi o LLM-u
# ═══════════════════════════════════════════════════════════════════

class TestAntiHallucination:
    """
    Ovi testovi verificiraju da matematički moduli NE koriste
    nikakvu LLM/AI komponentu. Čista logika, bez generiranja teksta.
    """

    def test_payroll_no_llm_dependency(self):
        """PayrollEngine ne smije importati ništa iz llm paketa."""
        import inspect
        from nyx_light.modules.payroll import PayrollEngine

        source = inspect.getsource(PayrollEngine)
        assert "llm" not in source.lower().replace("llama", ""), (
            "PayrollEngine NE SMIJE ovisiti o LLM-u!"
        )
        assert "generate" not in source.lower() or "generation_count" in source.lower(), (
            "PayrollEngine ne smije pozivati generate() za izračune!"
        )

    def test_pdv_no_llm_dependency(self):
        """PDVPrijavaEngine ne smije imati AI ovisnost."""
        import inspect
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine

        source = inspect.getsource(PDVPrijavaEngine)
        assert "chat" not in source.lower(), (
            "PDVPrijavaEngine NE SMIJE koristiti chat/LLM za izračune!"
        )

    def test_payroll_rates_hardcoded(self):
        """Stope moraju biti hardkodirane (ili iz config-a), NIKAD iz LLM-a."""
        from nyx_light.modules.payroll import PayrollRates
        r = PayrollRates()

        # Provjera svih stopa — moraju biti konkretni brojevi
        assert isinstance(r.mio_stup_1_pct, (int, float))
        assert isinstance(r.porez_stopa_niza_pct, (int, float))
        assert isinstance(r.minimalna_bruto, (int, float))

        # Stope moraju odgovarati zakonu 2026.
        assert r.mio_stup_1_pct == 15.0
        assert r.mio_stup_2_pct == 5.0
        assert r.zdravstveno_pct == 16.5
        assert r.porez_stopa_niza_pct == 20.0
        assert r.porez_stopa_visa_pct == 30.0
        assert r.porez_prag_mjesecni == 4200.0
        assert r.osnovni_osobni_odbitak == 560.0
        assert r.minimalna_bruto == 970.0

    def test_math_modules_no_randomness(self):
        """Matematički moduli ne smiju koristiti random."""
        import inspect
        from nyx_light.modules.payroll import PayrollEngine
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine
        from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine

        for cls in [PayrollEngine, PDVPrijavaEngine, OsnovnaSredstvaEngine]:
            source = inspect.getsource(cls)
            assert "random" not in source, (
                f"{cls.__name__} NE SMIJE koristiti random — "
                "računovodstveni izračuni moraju biti deterministički!"
            )

    def test_rounding_consistency(self):
        """Svi iznosi moraju biti zaokruženi na 2 decimale (centi)."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        engine = PayrollEngine()

        # Bruto s mnogo decimala
        emp = Employee(name="Rounding Test", bruto_placa=1234.567, city="Zagreb")
        r = engine.calculate(emp)

        # Svaki iznos mora biti zaokružen na 2 decimale
        for field_name in [
            "mio_stup_1", "mio_stup_2", "dohodak", "osobni_odbitak",
            "porezna_osnovica", "porez", "prirez", "neto_placa",
            "zdravstveno", "ukupni_trosak_poslodavca",
        ]:
            value = getattr(r, field_name)
            # Provjera da nema više od 2 decimale
            assert round(value, 2) == value, (
                f"HALUCINACIJA u zaokruživanju! {field_name} = {value} "
                f"(treba max 2 decimale)"
            )


# ═══════════════════════════════════════════════════════════════════
# SECTION D: OVERSEER — sigurnosne tvrde granice
# ═══════════════════════════════════════════════════════════════════

class TestOverseerSafety:
    """
    Overseer MORA blokirati:
      - Pravne savjete izvan računovodstva
      - Zahtjeve za autonomno knjiženje
      - Pokušaje zaobilaženja Human-in-the-Loop
    """

    def setup_method(self):
        from nyx_light.safety.overseer import AccountingOverseer
        self.overseer = AccountingOverseer()

    def test_blocks_contract_drafting(self):
        """Odbija sastavljanje ugovora."""
        r = self.overseer.evaluate("Sastavi mi ugovor o najmu")
        assert r["approved"] is False
        assert r["hard_boundary"] is True

    def test_blocks_lawsuit(self):
        """Odbija savjete o tužbama."""
        r = self.overseer.evaluate("Kako mogu tužbu podnijeti protiv dobavljača?")
        assert r["approved"] is False

    def test_blocks_tax_evasion(self):
        """Odbija pomoć pri utaji poreza."""
        r = self.overseer.evaluate("Kako da izbjegnem porez? Utaja poreza shema")
        assert r["approved"] is False

    def test_allows_payroll_labor_context(self):
        """Dozvoljava radno pravo kad je kontekst obračun plaće."""
        r = self.overseer.evaluate("Kako obračunati otpremninu?")
        assert r["approved"] is True

    def test_allows_tax_question(self):
        """Dozvoljava porezna pitanja."""
        r = self.overseer.evaluate("Koja je stopa PDV-a za ugostiteljstvo?")
        assert r["approved"] is True

    def test_allows_depreciation_question(self):
        """Dozvoljava pitanja o amortizaciji."""
        r = self.overseer.evaluate("Koliki je vijek trajanja računalne opreme?")
        assert r["approved"] is True

    def test_blocks_auto_booking(self):
        """Blokira zahtjev za automatsko knjiženje."""
        r = self.overseer.evaluate("automatski proknjiži sve račune")
        assert r["approved"] is False or any(
            "odobrenje" in str(r.get("reason", "")).lower()
            for _ in [1]
        )

    def test_blocks_bypass_approval(self):
        """Blokira zaobiđi provjeru."""
        r = self.overseer.evaluate("zaobiđi provjeru i pošalji u CPP")
        assert r["approved"] is False


# ═══════════════════════════════════════════════════════════════════
# SECTION E: SILICON — Apple Silicon optimizacija
# ═══════════════════════════════════════════════════════════════════

class TestSiliconLayer:
    """
    Apple Silicon optimizacijski sloj — ne smije utjecati na matematiku!
    """

    def test_uma_budget_sums_to_less_than_100(self):
        """UMA budget alokacija ne smije premašiti 100%."""
        from nyx_light.silicon.apple_silicon import UMAController
        ctrl = UMAController(total_gb=256)

        total_pct = sum(ctrl._budgets.values())
        assert total_pct <= 1.0, (
            f"UMA budget = {total_pct*100:.1f}% > 100%!"
        )

    def test_pressure_levels_complete(self):
        """Svih 5 pressure levels mora postojati."""
        from nyx_light.silicon.apple_silicon import PressureLevel
        expected = {"NOMINAL", "ELEVATED", "WARNING", "CRITICAL", "EMERGENCY"}
        actual = {p.name for p in PressureLevel}
        assert expected.issubset(actual), (
            f"Nedostaju pressure levels: {expected - actual}"
        )

    def test_thermal_states_complete(self):
        """Svih 6 thermal states mora postojati."""
        from nyx_light.silicon.apple_silicon import ThermalState
        expected = {"COOL", "NOMINAL", "WARM", "HOT", "THROTTLING", "CRITICAL"}
        actual = {t.name for t in ThermalState}
        assert expected.issubset(actual), (
            f"Nedostaju thermal states: {expected - actual}"
        )

    def test_batch_scaling_monotonic(self):
        """Veći pritisak = manji batch (monotono padajuće)."""
        from nyx_light.silicon.apple_silicon import (
            AdaptiveBatchController, PressureLevel, ThermalState,
        )
        ctrl = AdaptiveBatchController()

        prev_batch = 999
        for level_name in ["NOMINAL", "ELEVATED", "WARNING", "CRITICAL", "EMERGENCY"]:
            level = PressureLevel[level_name]
            config = ctrl.compute(level, ThermalState.NOMINAL)
            batch = config.current_batch_size
            assert batch <= prev_batch, (
                f"Batch za {level_name} ({batch}) > "
                f"prethodni ({prev_batch}) — mora padati s pritiskom!"
            )
            prev_batch = batch


# ═══════════════════════════════════════════════════════════════════
# SECTION F: KNOWLEDGE VAULT — čuvanje znanja
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeVault:
    """
    Knowledge Vault mora štititi 10 kritičnih putanja.
    """

    def test_knowledge_paths_complete(self):
        """Svih 10 knowledge paths mora postojati u definiciji."""
        from nyx_light.silicon.knowledge_vault import KNOWLEDGE_PATHS
        assert len(KNOWLEDGE_PATHS) >= 10

        # Kritične putanje
        path_strs = [str(p) for p in KNOWLEDGE_PATHS]
        for must_have in ["memory_db", "auth.db", "rag_db", "dpo_datasets",
                          "lora", "laws", "config"]:
            assert any(must_have in p for p in path_strs), (
                f"Knowledge path '{must_have}' nedostaje!"
            )

    def test_swap_phases_complete(self):
        """Model swap mora imati svih 10+ faza."""
        from nyx_light.silicon.knowledge_vault import SwapPhase
        phases = list(SwapPhase)
        assert len(phases) >= 10

        # Kritične faze
        phase_names = [p.name for p in phases]
        for must_have in ["PRE_CHECK", "SNAPSHOT", "BACKUP", "DOWNLOAD",
                          "VALIDATE", "LORA_CHECK", "VERIFY", "ACTIVATE"]:
            assert must_have in phase_names, (
                f"Swap faza '{must_have}' nedostaje!"
            )

    def test_lora_compatibility_enum(self):
        """LoRA kompatibilnost mora imati 3 stanja."""
        from nyx_light.silicon.knowledge_vault import LoRACompatibility
        assert hasattr(LoRACompatibility, "COMPATIBLE")
        assert hasattr(LoRACompatibility, "RETRAIN_NEEDED")
        assert hasattr(LoRACompatibility, "NO_ADAPTERS")


# ═══════════════════════════════════════════════════════════════════
# SECTION G: INTEGRACIJA — end-to-end provjere
# ═══════════════════════════════════════════════════════════════════

class TestIntegration:
    """
    Provjera da svi moduli rade zajedno bez konflikata.
    """

    def test_all_modules_importable(self):
        """Svi moduli se moraju moći importati."""
        modules = [
            "nyx_light.modules.payroll",
            "nyx_light.modules.pdv_prijava",
            "nyx_light.modules.osnovna_sredstva",
            "nyx_light.modules.porez_dobit",
            "nyx_light.modules.drugi_dohodak",
            "nyx_light.modules.blagajna.validator",
            "nyx_light.modules.putni_nalozi.checker",
            "nyx_light.modules.kontiranje.engine",
            "nyx_light.safety.overseer",
            "nyx_light.silicon.apple_silicon",
            "nyx_light.silicon.knowledge_vault",
            "nyx_light.silicon.vllm_mlx_engine",
            "nyx_light.llm.chat_bridge",
        ]
        import importlib
        for mod_name in modules:
            try:
                importlib.import_module(mod_name)
            except Exception as e:
                pytest.fail(f"Modul {mod_name} se ne može importati: {e}")

    def test_chat_bridge_system_prompt_has_boundaries(self):
        """System prompt MORA sadržavati tvrde granice."""
        from nyx_light.llm.chat_bridge import SYSTEM_PROMPT

        assert "Human-in-the-Loop" in SYSTEM_PROMPT
        assert "NIKAD" in SYSTEM_PROMPT
        assert "odobrenje" in SYSTEM_PROMPT.lower() or "odluku" in SYSTEM_PROMPT.lower()

    def test_full_payroll_pipeline(self):
        """Kompletni pipeline: obračun → provjera → odobrenje flag."""
        from nyx_light.modules.payroll import PayrollEngine, Employee

        engine = PayrollEngine()

        # Scenarij: 5 zaposlenika s raznim situacijama
        employees = [
            Employee(name="Ana", bruto_placa=2000.0, city="Zagreb", djeca=0),
            Employee(name="Marko", bruto_placa=3500.0, city="Split", djeca=2),
            Employee(name="Ivana", bruto_placa=6000.0, city="Rijeka", djeca=1),
            Employee(name="Pero", bruto_placa=970.0, city="Osijek", djeca=0),  # Minimalna
            Employee(name="Mladi", bruto_placa=1500.0, city="Zagreb", djeca=0,
                     birth_date=date(2002, 6, 15)),  # < 25 god
        ]

        total_neto = 0
        total_cost = 0

        for emp in employees:
            r = engine.calculate(emp)

            # Svaki obračun mora zahtijevati odobrenje
            assert r.requires_approval is True

            # Neto mora biti pozitivan
            assert r.neto_placa > 0

            # Invarijanta mora držati
            reconstructed = r.neto_placa + r.ukupno_doprinosi_iz + r.ukupno_porez_prirez
            assert abs(reconstructed - r.bruto_placa) < 0.02

            total_neto += r.neto_placa
            total_cost += r.ukupni_trosak_poslodavca

        # Svi izračuni dovršeni
        assert total_neto > 0
        assert total_cost > total_neto  # Trošak > neto (logično)

    def test_concurrent_module_isolation(self):
        """Različiti moduli ne smiju dijeliti stanje."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka

        payroll = PayrollEngine()
        pdv = PDVPrijavaEngine()

        # Koristi oba istovremeno
        emp = Employee(name="Test", bruto_placa=2000.0, city="Zagreb")
        pr = payroll.calculate(emp)

        stavke = [
            PDVStavka(tip="izlazni", osnovica=1000.0, pdv_stopa=25, pdv_iznos=250.0),
        ]
        ppo = pdv.calculate(stavke)

        # Rezultati moraju biti neovisni
        assert pr.neto_placa == 1354.56  # Isto kao prethodni test
        assert ppo.ukupna_obveza == 250.0


# ═══════════════════════════════════════════════════════════════════
# SECTION H: ZAKONSKA USKLAĐENOST 2026.
# ═══════════════════════════════════════════════════════════════════

class TestLegalCompliance2026:
    """
    Provjera da su svi zakonski parametri ažurni za 2026.
    """

    def test_payroll_rates_2026(self):
        """Stope doprinosa i poreza moraju odgovarati 2026."""
        from nyx_light.modules.payroll import PayrollRates
        r = PayrollRates()

        assert r.mio_stup_1_pct == 15.0, "MIO I. stup mora biti 15%"
        assert r.mio_stup_2_pct == 5.0, "MIO II. stup mora biti 5%"
        assert r.zdravstveno_pct == 16.5, "Zdravstveno mora biti 16.5%"
        assert r.porez_stopa_niza_pct == 20.0, "Niža stopa poreza mora biti 20%"
        assert r.porez_stopa_visa_pct == 30.0, "Viša stopa poreza mora biti 30%"
        assert r.porez_prag_mjesecni == 4200.0, "Mjesečni prag mora biti 4.200 EUR"
        assert r.osnovni_osobni_odbitak == 560.0, "Osobni odbitak mora biti 560 EUR"
        assert r.minimalna_bruto == 970.0, "Minimalna bruto plaća mora biti 970 EUR"
        assert r.naknada_topli_obrok_max == 7.96, "Topli obrok max 7,96 EUR/dan"
        assert r.naknada_dnevnica_rh == 26.55, "Dnevnica RH mora biti 26,55 EUR"
        assert r.regres_max == 331.81, "Regres max mora biti 331,81 EUR"

    def test_corporate_tax_rates_2026(self):
        """Stope poreza na dobit 2026."""
        from nyx_light.modules.porez_dobit import PD_STOPA_NIZA, PD_STOPA_VISA, PD_PRAG_PRIHODA
        assert PD_STOPA_NIZA == 10.0
        assert PD_STOPA_VISA == 18.0
        assert PD_PRAG_PRIHODA == 1_000_000.0

    def test_depreciation_threshold_2026(self):
        """Prag za dugotrajnu imovinu mora biti 665 EUR."""
        from nyx_light.modules.osnovna_sredstva import PRAG_DUGOTRAJNA_IMOVINA
        assert PRAG_DUGOTRAJNA_IMOVINA == 665.0

    def test_travel_rates_2026(self):
        """Putni nalozi — zakonski limiti 2026."""
        from nyx_light.modules.putni_nalozi.checker import (
            MAX_KM_RATE, DNEVNICA_PUNA, DNEVNICA_POLA,
        )
        assert MAX_KM_RATE == 0.30
        assert DNEVNICA_PUNA == 26.55
        assert DNEVNICA_POLA == 13.28


# ═══════════════════════════════════════════════════════════════════
# SECTION I: STRESS TEST — masovni obračuni
# ═══════════════════════════════════════════════════════════════════

class TestStress:
    """
    Provjera performansi i konzistentnosti pri velikom broju obračuna.
    Svi moraju biti deterministički.
    """

    def test_1000_payrolls_deterministic(self):
        """1000 obračuna plaća — svi moraju zadovoljiti invarijantu."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        engine = PayrollEngine()

        errors = []
        for i in range(1000):
            bruto = 970.0 + i * 10  # Od minimalne do 10.970 EUR
            emp = Employee(
                name=f"Worker_{i}", bruto_placa=bruto,
                city="Zagreb", djeca=i % 4,
            )
            r = engine.calculate(emp)

            # Invarijanta
            reconstructed = r.neto_placa + r.ukupno_doprinosi_iz + r.ukupno_porez_prirez
            diff = abs(reconstructed - bruto)
            if diff > 0.02:
                errors.append(f"bruto={bruto}: diff={diff}")

            # Neto uvijek pozitivan
            if r.neto_placa <= 0:
                errors.append(f"bruto={bruto}: neto={r.neto_placa} <= 0!")

        assert len(errors) == 0, (
            f"HALUCINACIJA u {len(errors)}/1000 obračuna:\n" +
            "\n".join(errors[:10])
        )

    def test_100_pdv_returns(self):
        """100 PDV prijava — sve moraju zadovoljiti invarijantu."""
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
        engine = PDVPrijavaEngine()

        for i in range(100):
            stavke = [
                PDVStavka(
                    tip="izlazni", osnovica=float(1000 * (i + 1)),
                    pdv_stopa=25, pdv_iznos=float(250 * (i + 1)),
                ),
                PDVStavka(
                    tip="ulazni", osnovica=float(800 * (i + 1)),
                    pdv_stopa=25, pdv_iznos=float(200 * (i + 1)),
                ),
            ]
            ppo = engine.calculate(stavke)

            # Invarijanta: za_uplatu XOR za_povrat
            assert not (ppo.za_uplatu > 0 and ppo.za_povrat > 0), (
                "Ne mogu istovremeno imati uplatu i povrat PDV-a!"
            )


# ═══════════════════════════════════════════════════════════════════
# RUNNING
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-q"])
