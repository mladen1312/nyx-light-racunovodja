"""
═══════════════════════════════════════════════════════════════════════════════
 Nyx Light — Sprint 15: RAČUNOVODSTVENI AI TEST SUITE
 
 KLJUČNI PRINCIP: Matematika ≠ AI
 ─────────────────────────────────
 ✅ MATEMATIČKA SKRIPTA radi: sve financijske kalkulacije
    (bruto→neto, PDV, amortizacija, porez na dobit, putni nalozi, blagajna)
 ✅ AI radi: klasifikaciju, kontiranje (prijedlog), NLP parsiranje, objašnjenja
 ✅ NIKADA: AI ne smije izmisliti broj — svaki iznos mora biti izračunat formulom
 ✅ UVIJEK: requires_approval = True (Human-in-the-Loop)
 
 Test kategorije:
 A. Payroll (bruto→neto obračun) — ČISTA MATEMATIKA
 B. PDV prijava — ČISTA MATEMATIKA
 C. Amortizacija — ČISTA MATEMATIKA
 D. Porez na dobit — ČISTA MATEMATIKA
 E. Putni nalozi — ČISTA MATEMATIKA + validacija
 F. Blagajna — ČISTA MATEMATIKA + AML provjera
 G. Kontiranje — AI GRANICA (prijedlog, ne kalkulacija)
 H. Anti-halucinacija — Verifikacija da AI ne generira brojeve
 I. Silicon / Knowledge Vault — Očuvanje znanja pri zamjeni modela
═══════════════════════════════════════════════════════════════════════════════
"""

import pytest
import sys
import os
from datetime import date, datetime
from decimal import Decimal

# Path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ═════════════════════════════════════════════════════════════
# A. PAYROLL — BRUTO → NETO OBRAČUN (ČISTA MATEMATIKA)
# ═════════════════════════════════════════════════════════════

class TestPayrollMath:
    """Verifikacija: SVAKI korak obračuna plaće je deterministička formula.
    
    Formula (ZoD, ZoPD 2026.):
    1. MIO I. stup = bruto × 15%
    2. MIO II. stup = bruto × 5% 
    3. Dohodak = bruto - MIO_ukupno
    4. Osobni odbitak = 560 EUR + faktori
    5. Porezna osnovica = max(0, dohodak - osobni_odbitak)
    6. Porez = 20% do 4.200 EUR + 30% iznad
    7. Prirez = porez × stopa_grada
    8. Neto = bruto - MIO - porez - prirez
    9. Zdravstveno = bruto × 16.5% (teret poslodavca)
    """

    def setup_method(self):
        from nyx_light.modules.payroll import PayrollEngine, Employee, PayrollRates
        self.engine = PayrollEngine()
        self.Employee = Employee
        self.PayrollRates = PayrollRates

    # ── Osnovni obračun: prosječna plaća ──
    def test_prosjecna_placa_1500_eur(self):
        """Bruto 1.500 EUR, Zagreb, bez djece."""
        emp = self.Employee(name="Test", bruto_placa=1500.0, city="Zagreb")
        r = self.engine.calculate(emp)

        # Ručni izračun:
        assert r.mio_stup_1 == 225.0      # 1500 × 15% = 225
        assert r.mio_stup_2 == 75.0       # 1500 × 5% = 75
        assert r.ukupno_doprinosi_iz == 300.0  # 225 + 75
        assert r.dohodak == 1200.0         # 1500 - 300
        assert r.osobni_odbitak == 560.0   # Osnovni (bez djece)
        assert r.porezna_osnovica == 640.0 # 1200 - 560
        # Porez: 640 × 20% = 128 (sve ispod 4.200 praga)
        assert r.porez == 128.0
        # Prirez Zagreb 18%: 128 × 18% = 23.04
        assert r.prirez == 23.04
        assert r.ukupno_porez_prirez == 151.04  # 128 + 23.04
        # Neto: 1500 - 300 - 151.04 = 1048.96
        assert r.neto_placa == 1048.96
        # Zdravstveno: 1500 × 16.5% = 247.50
        assert r.zdravstveno == 247.5
        # Ukupni trošak: 1500 + 247.50 = 1747.50
        assert r.ukupni_trosak_poslodavca == 1747.5
        assert r.requires_approval is True

    # ── Visoka plaća: progresivni porez ──
    def test_visoka_placa_6000_eur_split(self):
        """Bruto 6.000 EUR, Split — prelazi prag 4.200 EUR porezne osnovice."""
        emp = self.Employee(name="Director", bruto_placa=6000.0, city="Split")
        r = self.engine.calculate(emp)

        assert r.mio_stup_1 == 900.0      # 6000 × 15%
        assert r.mio_stup_2 == 300.0      # 6000 × 5%
        assert r.ukupno_doprinosi_iz == 1200.0
        assert r.dohodak == 4800.0         # 6000 - 1200
        assert r.osobni_odbitak == 560.0
        assert r.porezna_osnovica == 4240.0  # 4800 - 560

        # Progresivni porez:
        # Do 4.200 → 4200 × 20% = 840
        # Iznad 4.200 → (4240-4200) × 30% = 40 × 30% = 12
        # Ukupno: 840 + 12 = 852
        assert r.porez == 852.0

        # Prirez Split 15%: 852 × 15% = 127.80
        assert r.prirez == 127.8
        assert r.ukupno_porez_prirez == 979.8  # 852 + 127.80

        # Neto: 6000 - 1200 - 979.80 = 3820.20
        assert r.neto_placa == 3820.2

    # ── Djeca: progresivni faktori osobnog odbitka ──
    def test_placa_sa_djecom(self):
        """Bruto 2.000 EUR, Zagreb, 2 djece."""
        emp = self.Employee(name="Roditelj", bruto_placa=2000.0, city="Zagreb", djeca=2)
        r = self.engine.calculate(emp)

        # Osobni odbitak: 560 + (0.7×560) + (1.0×560) = 560 + 392 + 560 = 1512
        assert r.osobni_odbitak == 1512.0

        assert r.dohodak == 1600.0  # 2000 - 400
        assert r.porezna_osnovica == 88.0  # 1600 - 1512
        # Porez: 88 × 20% = 17.60
        assert r.porez == 17.6
        # Prirez Zagreb 18%: 17.60 × 18% = 3.17
        assert r.prirez == 3.17
        # Ukupno porez+prirez: 20.77
        assert r.ukupno_porez_prirez == 20.77
        # Neto: 2000 - 400 - 20.77 = 1579.23
        assert r.neto_placa == 1579.23

    # ── 3 djece — viši faktori ──
    def test_placa_3_djece(self):
        """Osobni odbitak: 560 + 0.7×560 + 1.0×560 + 1.4×560 = 560+392+560+784 = 2296."""
        emp = self.Employee(name="Troje", bruto_placa=2500.0, city="Zagreb", djeca=3)
        r = self.engine.calculate(emp)
        assert r.osobni_odbitak == 2296.0

    # ── 4 djece ──
    def test_placa_4_djece(self):
        """Osobni odbitak: 560 + 0.7×560 + 1.0×560 + 1.4×560 + 1.9×560 = 560+392+560+784+1064 = 3360."""
        emp = self.Employee(name="Cetiri", bruto_placa=3000.0, city="Zagreb", djeca=4)
        r = self.engine.calculate(emp)
        assert r.osobni_odbitak == 3360.0

    # ── Uzdržavani članovi ──
    def test_uzdrzavani_clanovi(self):
        """Osobni odbitak s uzdržavanim članom: 560 + 0.7×560 = 952."""
        emp = self.Employee(name="Suprug", bruto_placa=1500.0, city="Zagreb",
                            uzdrzavani_clanovi=1)
        r = self.engine.calculate(emp)
        assert r.osobni_odbitak == 952.0

    # ── Bez II. stupa (stariji radnik) ──
    def test_bez_drugog_stupa(self):
        """Radnik bez II. stupa — sav MIO (20%) ide u I. stup."""
        emp = self.Employee(name="Senior", bruto_placa=1500.0, city="Zagreb",
                            mio_stup_2=False)
        r = self.engine.calculate(emp)
        # 20% sve u I. stup
        assert r.mio_stup_1 == 300.0  # 1500 × 20%
        assert r.mio_stup_2 == 0.0
        assert r.ukupno_doprinosi_iz == 300.0  # Isti ukupni iznos

    # ── Minimalna plaća ──
    def test_minimalna_placa_warning(self):
        """Bruto ispod minimalne (970 EUR 2026.) — mora biti warning."""
        emp = self.Employee(name="Pod", bruto_placa=800.0, city="Zagreb")
        r = self.engine.calculate(emp)
        assert any("ispod minimalne" in w for w in r.warnings)

    # ── Mladi do 25 (100% oslobođenje poreza) ──
    def test_olaksica_mladi_do_25(self):
        """Radnik mlađi od 25 — 100% oslobođenje poreza i prireza."""
        emp = self.Employee(name="Mladi", bruto_placa=1500.0, city="Zagreb",
                            birth_date=date(2003, 6, 15))
        r = self.engine.calculate(emp)
        # Porez se izračuna ali olakšica ga poništava
        assert r.olaksica_mladi_pct == 100.0
        assert r.ukupno_porez_prirez == 0.0
        # Neto = bruto - MIO (nema poreza)
        assert r.neto_placa == 1200.0  # 1500 - 300

    # ── Mladi 25-30 (50% oslobođenje) ──
    def test_olaksica_mladi_25_30(self):
        """Radnik 25-30 — 50% oslobođenje poreza."""
        emp = self.Employee(name="Mladi2", bruto_placa=1500.0, city="Zagreb",
                            birth_date=date(1998, 1, 1))
        r = self.engine.calculate(emp)
        assert r.olaksica_mladi_pct == 50.0
        # Porez+prirez bi bio 151.04, olakšica 50% → 75.52
        assert r.ukupno_porez_prirez == 75.52

    # ── Invalid — dodatni faktor na odbitak ──
    def test_invalid_radnik(self):
        """Radnik invalid — +0.4×560 na osobni odbitak."""
        emp = self.Employee(name="Invalid", bruto_placa=1500.0, city="Zagreb",
                            invalid=True)
        r = self.engine.calculate(emp)
        # 560 + 0.4×560 = 560 + 224 = 784
        assert r.osobni_odbitak == 784.0

    # ── Grad bez prireza ──
    def test_grad_bez_prireza(self):
        """Grad koji nije u bazi — prirez 0%."""
        emp = self.Employee(name="Selo", bruto_placa=1500.0, city="Mala Vas")
        r = self.engine.calculate(emp)
        assert r.prirez == 0.0
        assert r.ukupno_porez_prirez == r.porez

    # ── Ugovor o djelu ──
    def test_ugovor_o_djelu(self):
        """Drugi dohodak — fiksne stope."""
        result = self.engine.calculate_ugovor_o_djelu(bruto_naknada=1000.0)
        # MIO I: 1000 × 7.5% = 75
        assert result["mio_stup_1"] == 75.0
        # MIO II: 1000 × 2.5% = 25
        assert result["mio_stup_2"] == 25.0
        # Zdravstveno: 1000 × 7.5% = 75
        assert result["zdravstveno"] == 75.0
        # Dohodak: 1000 - 75 - 25 - 75 = 825
        assert result["dohodak"] == 825.0
        # Porez: 825 × 20% = 165
        assert result["porez"] == 165.0
        # Neto: 1000 - 75 - 25 - 75 - 165 = 660
        assert result["neto"] == 660.0
        assert result["requires_approval"] is True

    # ── Autorski honorar ──
    def test_autorski_honorar(self):
        """Autorski honorar s 30% normiranim troškovima."""
        result = self.engine.calculate_autorski_honorar(bruto_honorar=2000.0)
        # Normirani trošak: 2000 × 30% = 600
        assert result["normirani_trosak"] == 600.0
        # Osnovica: 2000 - 600 = 1400
        assert result["osnovica_za_doprinose"] == 1400.0
        # MIO I: 1400 × 7.5% = 105
        assert result["mio_stup_1"] == 105.0
        # MIO II: 1400 × 2.5% = 35
        assert result["mio_stup_2"] == 35.0
        # Zdravstveno: 1400 × 7.5% = 105
        assert result["zdravstveno"] == 105.0
        # Dohodak: 1400 - 105 - 35 - 105 = 1155
        assert result["dohodak"] == 1155.0
        # Porez: 1155 × 20% = 231
        assert result["porez"] == 231.0
        # Neto: 2000 - 105 - 35 - 105 - 231 = 1524
        assert result["neto"] == 1524.0
        assert result["requires_approval"] is True

    # ── Neoporezive naknade ──
    def test_neoporezive_naknade(self):
        """Provjera limita neoporezivih naknada (Pravilnik 2026.)."""
        naknade = self.engine.neoporezive_naknade(radnih_dana=22)
        # Topli obrok: 7.96 × 22 = 175.12
        assert naknade["topli_obrok_max"] == 175.12
        assert naknade["dnevnica_rh_puna"] == 26.55
        assert naknade["dnevnica_rh_pola"] == 13.28
        assert naknade["dar_dijete_god"] == 133.0
        assert naknade["regres_god"] == 331.81

    # ── Konzistentnost: bruto = neto + MIO + porez + prirez ──
    def test_bilanca_bruto_neto(self):
        """KRITIČNI TEST: bruto mora biti TOČNO jednak zbroju komponenti."""
        for bruto in [970.0, 1200.0, 1500.0, 2000.0, 3000.0, 5000.0, 8000.0, 15000.0]:
            emp = self.Employee(name="Bilanca", bruto_placa=bruto, city="Zagreb")
            r = self.engine.calculate(emp)
            # bruto = neto + MIO + porez + prirez
            reconstructed = round(r.neto_placa + r.ukupno_doprinosi_iz + r.ukupno_porez_prirez, 2)
            assert reconstructed == bruto, (
                f"HALUCINACIJA! bruto={bruto}, ali neto+MIO+porez={reconstructed}"
            )


# ═════════════════════════════════════════════════════════════
# B. PDV PRIJAVA — ČISTA MATEMATIKA
# ═════════════════════════════════════════════════════════════

class TestPDVMath:
    """Verifikacija PDV kalkulacija — nijedan broj ne smije biti AI-generiran."""

    def setup_method(self):
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
        self.engine = PDVPrijavaEngine()
        self.PDVStavka = PDVStavka

    def test_osnovni_pdv_25(self):
        """Jedan izlazni račun s 25% PDV."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=1000.0, pdv_stopa=25, pdv_iznos=250.0)
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.izlazni_25_osnovica == 1000.0
        assert ppo.izlazni_25_pdv == 250.0
        assert ppo.ukupna_obveza == 250.0
        assert ppo.ukupni_pretporez == 0.0
        assert ppo.za_uplatu == 250.0

    def test_pretporez_i_obveza(self):
        """Izlazni + ulazni = razlika za uplatu/povrat."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=5000.0, pdv_stopa=25, pdv_iznos=1250.0),
            self.PDVStavka(tip="ulazni", osnovica=3000.0, pdv_stopa=25, pdv_iznos=750.0),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.ukupna_obveza == 1250.0
        assert ppo.ukupni_pretporez == 750.0
        # Razlika: 1250 - 750 = 500 za uplatu
        assert ppo.za_uplatu == 500.0
        assert ppo.za_povrat == 0.0

    def test_povrat_pdv(self):
        """Pretporez veći od obveze — povrat."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=1000.0, pdv_stopa=25, pdv_iznos=250.0),
            self.PDVStavka(tip="ulazni", osnovica=5000.0, pdv_stopa=25, pdv_iznos=1250.0),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.za_uplatu == 0.0
        assert ppo.za_povrat == 1000.0  # 1250 - 250

    def test_vise_stopa_pdv(self):
        """Mix stopa: 25%, 13%, 5%."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=1000.0, pdv_stopa=25, pdv_iznos=250.0),
            self.PDVStavka(tip="izlazni", osnovica=2000.0, pdv_stopa=13, pdv_iznos=260.0),
            self.PDVStavka(tip="izlazni", osnovica=500.0, pdv_stopa=5, pdv_iznos=25.0),
            self.PDVStavka(tip="ulazni", osnovica=800.0, pdv_stopa=25, pdv_iznos=200.0),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.izlazni_25_osnovica == 1000.0
        assert ppo.izlazni_13_osnovica == 2000.0
        assert ppo.izlazni_5_osnovica == 500.0
        # Obveza: 250 + 260 + 25 = 535
        assert ppo.ukupna_obveza == 535.0
        # Pretporez: 200
        assert ppo.ukupni_pretporez == 200.0
        # Za uplatu: 535 - 200 = 335
        assert ppo.za_uplatu == 335.0

    def test_eu_reverse_charge(self):
        """EU transakcija — reverse charge ne ulazi u obveza/pretporez direktno."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=10000.0, pdv_stopa=0,
                           eu_transakcija=True, reverse_charge=True),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.eu_isporuke_osnovica == 10000.0
        assert ppo.reverse_charge_izdani == 10000.0
        # Ne ulazi u izlazni PDV
        assert ppo.izlazni_25_pdv == 0.0

    def test_bilanca_pdv_formula(self):
        """KRITIČNI TEST: za_uplatu = obveza - pretporez (kad > 0)."""
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=10000.0, pdv_stopa=25, pdv_iznos=2500.0),
            self.PDVStavka(tip="izlazni", osnovica=3000.0, pdv_stopa=13, pdv_iznos=390.0),
            self.PDVStavka(tip="ulazni", osnovica=8000.0, pdv_stopa=25, pdv_iznos=2000.0),
            self.PDVStavka(tip="ulazni", osnovica=1000.0, pdv_stopa=5, pdv_iznos=50.0),
        ]
        ppo = self.engine.calculate(stavke)
        razlika = round(ppo.ukupna_obveza - ppo.ukupni_pretporez, 2)
        if razlika > 0:
            assert ppo.za_uplatu == razlika
            assert ppo.za_povrat == 0.0
        else:
            assert ppo.za_povrat == abs(razlika)
            assert ppo.za_uplatu == 0.0


# ═════════════════════════════════════════════════════════════
# C. AMORTIZACIJA — ČISTA MATEMATIKA
# ═════════════════════════════════════════════════════════════

class TestAmortizacijaMath:
    """Linearna amortizacija — deterministička formula, bez AI."""

    def setup_method(self):
        from nyx_light.modules.osnovna_sredstva import (
            OsnovnaSredstvaEngine, PRAG_DUGOTRAJNA_IMOVINA, AMORTIZACIJSKE_STOPE
        )
        self.engine = OsnovnaSredstvaEngine()
        self.PRAG = PRAG_DUGOTRAJNA_IMOVINA
        self.STOPE = AMORTIZACIJSKE_STOPE

    def test_prag_sitan_inventar(self):
        """Nabavna < 665 EUR → sitan inventar, jednokratni otpis."""
        result = self.engine.add_asset({
            "naziv": "Miš", "nabavna_vrijednost": 50.0, "vrsta": "uredska_oprema"
        })
        assert result["status"] == "sitan_inventar"
        assert result["jednokratni_otpis"] is True

    def test_prag_granica(self):
        """Nabavna = 664.99 → sitan inventar."""
        result = self.engine.add_asset({
            "naziv": "Tipkovnica", "nabavna_vrijednost": 664.99
        })
        assert result["status"] == "sitan_inventar"

    def test_prag_dugotrajna(self):
        """Nabavna = 665 EUR → dugotrajna imovina."""
        result = self.engine.add_asset({
            "naziv": "Monitor", "nabavna_vrijednost": 665.0, "vrsta": "računalna_oprema"
        })
        assert result["status"] == "added"

    def test_amortizacija_racunalna_oprema(self):
        """Računalna oprema: 50% godišnje, vijek 2 godine."""
        result = self.engine.add_asset({
            "naziv": "Laptop", "nabavna_vrijednost": 2000.0, "vrsta": "računalna_oprema"
        })
        assert result["godisnja_stopa"] == 50.0
        assert result["korisni_vijek"] == 2
        # Godišnja: 2000 × 50% = 1000
        assert result["godisnja_amortizacija"] == 1000.0
        # Mjesečna: 1000 / 12 = 83.33
        assert result["mjesecna_amortizacija"] == 83.33

    def test_amortizacija_osobni_automobil(self):
        """Osobni automobil: 20% godišnje, vijek 5 godina."""
        result = self.engine.add_asset({
            "naziv": "Auto", "nabavna_vrijednost": 30000.0, "vrsta": "osobni_automobili"
        })
        assert result["godisnja_stopa"] == 20.0
        # Godišnja: 30000 × 20% = 6000
        assert result["godisnja_amortizacija"] == 6000.0
        # Mjesečna: 6000 / 12 = 500
        assert result["mjesecna_amortizacija"] == 500.0

    def test_amortizacija_nekretnina(self):
        """Građevinski objekt: 5% godišnje, vijek 20 godina."""
        result = self.engine.add_asset({
            "naziv": "Ured", "nabavna_vrijednost": 200000.0, "vrsta": "građevinski_objekti"
        })
        assert result["godisnja_stopa"] == 5.0
        assert result["korisni_vijek"] == 20
        # Godišnja: 200000 × 5% = 10000
        assert result["godisnja_amortizacija"] == 10000.0
        # Mjesečna: 10000 / 12 = 833.33
        assert result["mjesecna_amortizacija"] == 833.33

    def test_mjesecna_amortizacija_batch(self):
        """Batch mjesečna amortizacija — formula za svako sredstvo."""
        self.engine.add_asset({
            "naziv": "Laptop", "nabavna_vrijednost": 2400.0, "vrsta": "računalna_oprema"
        })
        self.engine.add_asset({
            "naziv": "Stol", "nabavna_vrijednost": 1200.0, "vrsta": "namjestaj"
        })
        results = self.engine.calculate_monthly_depreciation()
        assert len(results) == 2
        # Laptop: 2400 × 50% / 12 = 100
        assert results[0]["mjesecna_amortizacija"] == 100.0
        # Stol: 1200 × 20% / 12 = 20
        assert results[1]["mjesecna_amortizacija"] == 20.0

    def test_stope_svih_kategorija(self):
        """Verifikacija svih amortizacijskih stopa prema Pravilniku."""
        expected = {
            "građevinski_objekti": 5.0,
            "osobni_automobili": 20.0,
            "teretna_vozila": 25.0,
            "računalna_oprema": 50.0,
            "uredska_oprema": 25.0,
            "namjestaj": 20.0,
            "strojevi_oprema": 20.0,
            "software": 50.0,
            "licence_patenti": 25.0,
            "alati": 20.0,
            "telekomunikacijska_oprema": 20.0,
        }
        for vrsta, stopa in expected.items():
            assert self.STOPE[vrsta]["stopa"] == stopa, \
                f"Stopa za {vrsta}: očekivano {stopa}, dobiveno {self.STOPE[vrsta]['stopa']}"


# ═════════════════════════════════════════════════════════════
# D. POREZ NA DOBIT — ČISTA MATEMATIKA
# ═════════════════════════════════════════════════════════════

class TestPorezDobitMath:
    """PD obrazac — svaki red izračunat formulom."""

    def setup_method(self):
        from nyx_light.modules.porez_dobit import PorezDobitiEngine
        self.engine = PorezDobitiEngine()

    def test_mala_firma_10_posto(self):
        """Prihodi ≤ 1M EUR → stopa 10%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=500_000.0,
            ukupni_rashodi=400_000.0,
        )
        assert pd.dobit_prije_oporezivanja == 100_000.0
        assert pd.stopa == 10.0
        assert pd.porezna_osnovica == 100_000.0
        # Porez: 100000 × 10% = 10000
        assert pd.porez_na_dobit == 10_000.0

    def test_velika_firma_18_posto(self):
        """Prihodi > 1M EUR → stopa 18%."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=2_000_000.0,
            ukupni_rashodi=1_500_000.0,
        )
        assert pd.dobit_prije_oporezivanja == 500_000.0
        assert pd.stopa == 18.0
        # Porez: 500000 × 18% = 90000
        assert pd.porez_na_dobit == 90_000.0

    def test_uvecanja_i_umanjenja(self):
        """Reprezentacija i dividende utječu na poreznu osnovicu."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=800_000.0,
            ukupni_rashodi=700_000.0,
            uvecanja={"reprezentacija_50pct": 5_000.0, "kazne": 2_000.0},
            umanjenja={"dividende": 3_000.0},
        )
        # Dobit: 100000
        assert pd.dobit_prije_oporezivanja == 100_000.0
        # Uvećanja: 5000 + 2000 = 7000
        assert pd.ukupna_uvecanja == 7_000.0
        # Umanjenja: 3000
        assert pd.ukupna_umanjenja == 3_000.0
        # Osnovica: 100000 + 7000 - 3000 = 104000
        assert pd.porezna_osnovica == 104_000.0
        # 10% (prihodi < 1M): 104000 × 10% = 10400
        assert pd.porez_na_dobit == 10_400.0

    def test_predujmovi_razlika(self):
        """Plaćeni predujmovi → razlika za uplatu ili povrat."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=600_000.0,
            ukupni_rashodi=500_000.0,
            placeni_predujmovi=8_000.0,
        )
        # Porez: 100000 × 10% = 10000
        assert pd.porez_na_dobit == 10_000.0
        # Razlika: 10000 - 8000 = 2000 za uplatu
        assert pd.razlika_za_uplatu == 2_000.0

    def test_predujmovi_povrat(self):
        """Predujmovi veći od poreza → povrat."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=600_000.0,
            ukupni_rashodi=500_000.0,
            placeni_predujmovi=12_000.0,
        )
        assert pd.porez_na_dobit == 10_000.0
        assert pd.razlika_za_povrat == 2_000.0  # 12000 - 10000
        assert pd.razlika_za_uplatu == 0.0

    def test_gubitak_nema_poreza(self):
        """Rashodi > prihodi → porezna osnovica 0, porez 0."""
        pd = self.engine.calculate(
            godina=2025,
            ukupni_prihodi=400_000.0,
            ukupni_rashodi=500_000.0,
        )
        assert pd.dobit_prije_oporezivanja == -100_000.0
        assert pd.porezna_osnovica == 0.0
        assert pd.porez_na_dobit == 0.0

    def test_prag_granica(self):
        """Prihodi TOČNO 1M → stopa 10%."""
        pd = self.engine.calculate(
            godina=2025, ukupni_prihodi=1_000_000.0, ukupni_rashodi=900_000.0
        )
        assert pd.stopa == 10.0

    def test_prag_iznad(self):
        """Prihodi 1.000.001 → stopa 18%."""
        pd = self.engine.calculate(
            godina=2025, ukupni_prihodi=1_000_001.0, ukupni_rashodi=900_000.0
        )
        assert pd.stopa == 18.0


# ═════════════════════════════════════════════════════════════
# E. PUTNI NALOZI — MATEMATIKA + VALIDACIJA
# ═════════════════════════════════════════════════════════════

class TestPutniNaloziMath:
    """Km naknada, dnevnice, reprezentacija — formule, ne AI."""

    def setup_method(self):
        from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker, PutniNalog
        self.checker = PutniNalogChecker()
        self.PutniNalog = PutniNalog

    def test_km_naknada_standardna(self):
        """150 km × 0.30 EUR/km = 45.00 EUR."""
        pn = self.PutniNalog(djelatnik="Test", km=150.0, km_naknada=0.30)
        r = self.checker.validate_full(pn)
        assert r.km_naknada_ukupno == 45.0

    def test_km_naknada_prekoracenje(self):
        """Naknada iznad 0.30 → warning, ali računa s max 0.30."""
        pn = self.PutniNalog(djelatnik="Test", km=100.0, km_naknada=0.50)
        r = self.checker.validate_full(pn)
        # Koristi max 0.30
        assert r.km_naknada_ukupno == 30.0  # 100 × 0.30
        assert any("max" in w.lower() or "0.30" in w for w in r.warnings)

    def test_dnevnica_prekoracenje(self):
        """Dnevnica iznad 26.55 EUR → warning."""
        pn = self.PutniNalog(djelatnik="Test", dnevnica=40.0)
        r = self.checker.validate_full(pn)
        assert any("26.55" in w for w in r.warnings)

    def test_reprezentacija_50_posto_nepriznato(self):
        """Reprezentacija — 50% porezno nepriznato."""
        pn = self.PutniNalog(djelatnik="Test", reprezentacija=200.0)
        r = self.checker.validate_full(pn)
        assert r.ukupno_porezno_nepriznato == 100.0  # 200 × 50%
        assert any("50%" in w for w in r.warnings)

    def test_nedostaje_djelatnik(self):
        """Bez djelatnika → error, invalid."""
        pn = self.PutniNalog(djelatnik="", km=100.0)
        r = self.checker.validate_full(pn)
        assert r.valid is False
        assert any("djelatnik" in e.lower() for e in r.errors)

    def test_legacy_api_kompatibilnost(self):
        """Stari API validate() mora raditi."""
        result = self.checker.validate(km=100, km_naknada=0.30)
        assert "valid" in result
        assert result["naknada_ukupno"] == 30.0


# ═════════════════════════════════════════════════════════════
# F. BLAGAJNA — AML LIMIT + STANJE
# ═════════════════════════════════════════════════════════════

class TestBlagajnaMath:
    """AML limit 10.000 EUR — zakonska zabrana, ne AI odluka."""

    def setup_method(self):
        from nyx_light.modules.blagajna.validator import BlagajnaValidator, BlagajnaTx
        self.validator = BlagajnaValidator()
        self.BlagajnaTx = BlagajnaTx

    def test_aml_limit_10000(self):
        """Transakcija >= 10.000 EUR → ZABRANA (AML čl. 30.)."""
        tx = self.BlagajnaTx(iznos=10_000.0, vrsta="isplata")
        r = self.validator.validate_transaction(tx)
        assert any("AML" in e or "ZABRANA" in e for e in r.errors)

    def test_ispod_aml_limita(self):
        """Transakcija 9.999,99 EUR → OK."""
        tx = self.BlagajnaTx(iznos=9_999.99, vrsta="isplata")
        r = self.validator.validate_transaction(tx)
        # Ne smije biti AML error
        aml_errors = [e for e in r.errors if "AML" in e or "ZABRANA" in e]
        assert len(aml_errors) == 0

    def test_legacy_api(self):
        """Stari API validate() backward compatible."""
        result = self.validator.validate(iznos=5000.0, tip="isplata")
        assert "valid" in result


# ═════════════════════════════════════════════════════════════
# G. KONTIRANJE — AI GRANICA
# ═════════════════════════════════════════════════════════════

class TestKontiranjeAIBoundary:
    """Kontiranje je AI prijedlog — NIKADA ne izračunava iznose.
    
    AI radi: klasifikaciju (koji konto)
    Math radi: iznose, PDV, amortizaciju
    """

    def setup_method(self):
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        self.engine = KontiranjeEngine()

    def test_prijedlog_konta_materijal(self):
        """AI predlaže konto — uvijek requires_approval."""
        result = self.engine.suggest_konto("Nabava materijala za proizvodnju")
        assert result["requires_approval"] is True
        assert "suggested_konto" in result
        assert "confidence" in result
        # Konto mora biti iz kontnog plana (string, ne broj koji AI izmisli)
        assert isinstance(result["suggested_konto"], str)
        assert len(result["suggested_konto"]) == 4  # 4-digit konto

    def test_prijedlog_usluge(self):
        """Usluge → konto 4120 (RRIF: usluge rashod)."""
        result = self.engine.suggest_konto("Servis klima uređaja")
        assert result["suggested_konto"] in ("4120", "7200")  # 4120 RRIF, 7200 alt
        assert result["requires_approval"] is True

    def test_prijedlog_amortizacija(self):
        """Amortizacija → konto 4302 (RRIF: amortizacija opreme)."""
        result = self.engine.suggest_konto("Amortizacija računalne opreme")
        assert result["suggested_konto"] in ("4302", "7300")  # 4302 RRIF, 7300 alt
        assert result["requires_approval"] is True

    def test_niska_pouzdanost_fallback(self):
        """Nepoznat opis → konto 7800 (ostalo), niska pouzdanost."""
        result = self.engine.suggest_konto("Nešto potpuno nepoznato")
        assert result["confidence"] < 0.5
        assert result["requires_approval"] is True

    def test_memorija_L2_override(self):
        """L2 memorija ima prioritet nad AI prijedlogom."""
        memory = {"hint": "4120", "confidence": 0.95}
        result = self.engine.suggest_konto("Nabava", memory_hint=memory)
        assert result["suggested_konto"] == "4120"
        assert result["source"] == "L2_semantic_memory"
        assert result["requires_approval"] is True

    def test_ai_nikada_ne_generira_iznos(self):
        """KRITIČNO: kontiranje NIKADA ne vraća iznos — to radi druga skripta."""
        result = self.engine.suggest_konto("Račun za printer 500 EUR")
        # Nema "iznos", "amount", "total" u rezultatu
        for key in result:
            assert key not in ("iznos", "amount", "total", "pdv", "neto", "bruto"), \
                f"HALUCINACIJA! Kontiranje engine vratio '{key}' — AI NE SMIJE generirati iznose!"


# ═════════════════════════════════════════════════════════════
# H. ANTI-HALUCINACIJA — CROSS-VERIFICATION
# ═════════════════════════════════════════════════════════════

class TestAntiHalucinacija:
    """Verifikacija da NIJEDAN finansijski modul ne može halucinirati.
    
    Princip: svaki broj u outputu mora biti izračunat formulom.
    AI = klasifikacija, tekst, prijedlog
    Math = iznosi, postoci, porezi, naknade
    """

    def test_payroll_sve_polja_su_formule(self):
        """Svako numeričko polje u PayrollResult mora biti izvedeno iz bruto + stopa."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        engine = PayrollEngine()
        emp = Employee(name="Audit", bruto_placa=2000.0, city="Zagreb")
        r = engine.calculate(emp)

        bruto = 2000.0
        rates = engine.rates

        # Svaki broj je FORMULA, ne AI:
        assert r.mio_stup_1 == round(bruto * rates.mio_stup_1_pct / 100, 2)
        assert r.mio_stup_2 == round(bruto * rates.mio_stup_2_pct / 100, 2)
        assert r.dohodak == round(bruto - r.ukupno_doprinosi_iz, 2)
        assert r.porezna_osnovica == max(0, round(r.dohodak - r.osobni_odbitak, 2))
        assert r.zdravstveno == round(bruto * rates.zdravstveno_pct / 100, 2)
        assert r.ukupni_trosak_poslodavca == round(bruto + r.zdravstveno, 2)

    def test_pdv_svi_iznosi_su_zbroj_stavki(self):
        """PDV prijava — ukupni su uvijek SUM(stavke), nikad AI procjena."""
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
        engine = PDVPrijavaEngine()

        stavke = [
            PDVStavka(tip="izlazni", osnovica=1000, pdv_stopa=25, pdv_iznos=250),
            PDVStavka(tip="izlazni", osnovica=2000, pdv_stopa=13, pdv_iznos=260),
            PDVStavka(tip="ulazni", osnovica=1500, pdv_stopa=25, pdv_iznos=375),
        ]
        ppo = engine.calculate(stavke)

        # Obveza = SUM izlaznih PDV iznosa
        assert ppo.ukupna_obveza == round(250.0 + 260.0, 2)
        # Pretporez = SUM ulaznih PDV iznosa
        assert ppo.ukupni_pretporez == 375.0
        # Razlika = obveza - pretporez (formula, ne AI)
        assert ppo.za_uplatu == round(510.0 - 375.0, 2)

    def test_amortizacija_formula_linearna(self):
        """Amortizacija = nabavna_vrijednost × stopa / 100 / 12 — UVIJEK."""
        from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine
        engine = OsnovnaSredstvaEngine()

        test_cases = [
            ("računalna_oprema", 3000.0, 50.0),
            ("osobni_automobili", 25000.0, 20.0),
            ("namjestaj", 5000.0, 20.0),
            ("software", 10000.0, 50.0),
        ]

        for vrsta, nabavna, expected_stopa in test_cases:
            result = engine.add_asset({
                "naziv": f"Test {vrsta}",
                "nabavna_vrijednost": nabavna,
                "vrsta": vrsta,
            })
            god_amort = round(nabavna * expected_stopa / 100, 2)
            mj_amort = round(god_amort / 12, 2)

            assert result["godisnja_amortizacija"] == god_amort, \
                f"{vrsta}: godišnja {result['godisnja_amortizacija']} != {god_amort}"
            assert result["mjesecna_amortizacija"] == mj_amort, \
                f"{vrsta}: mjesečna {result['mjesecna_amortizacija']} != {mj_amort}"

    def test_porez_dobit_formula_verifikacija(self):
        """PD: porezna_osnovica = dobit + uvećanja - umanjenja (formula)."""
        from nyx_light.modules.porez_dobit import PorezDobitiEngine
        engine = PorezDobitiEngine()

        pd = engine.calculate(
            godina=2025,
            ukupni_prihodi=800_000,
            ukupni_rashodi=600_000,
            uvecanja={"reprezentacija_50pct": 10_000, "kazne": 5_000},
            umanjenja={"dividende": 3_000},
        )

        # Verifikacija svake formule:
        assert pd.dobit_prije_oporezivanja == 800_000 - 600_000
        assert pd.ukupna_uvecanja == 10_000 + 5_000
        assert pd.ukupna_umanjenja == 3_000
        assert pd.porezna_osnovica == 200_000 + 15_000 - 3_000  # 212000
        assert pd.porez_na_dobit == round(212_000 * 10.0 / 100, 2)  # 21200

    def test_requires_approval_svugdje(self):
        """KRITIČNO: Svaki modul mora imati requires_approval = True."""
        from nyx_light.modules.payroll import PayrollEngine, Employee
        from nyx_light.modules.porez_dobit import PorezDobitiEngine
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine

        # Payroll
        pe = PayrollEngine()
        r = pe.calculate(Employee(name="X", bruto_placa=1500.0))
        assert r.requires_approval is True, "PAYROLL mora zahtijevati odobrenje!"

        # Ugovor o djelu
        uod = pe.calculate_ugovor_o_djelu(1000.0)
        assert uod["requires_approval"] is True

        # Autorski honorar
        ah = pe.calculate_autorski_honorar(2000.0)
        assert ah["requires_approval"] is True

        # Kontiranje
        ke = KontiranjeEngine()
        k = ke.suggest_konto("test")
        assert k["requires_approval"] is True

    def test_roundtrip_precision(self):
        """Svi iznosi zaokruženi na 2 decimale — nema floating point greški."""
        from nyx_light.modules.payroll import PayrollEngine, Employee

        engine = PayrollEngine()
        # Testiraj s "problematičnim" iznosima za floating point
        test_amounts = [1333.33, 2666.67, 999.99, 1111.11, 7777.77]

        for bruto in test_amounts:
            emp = Employee(name="FP", bruto_placa=bruto, city="Zagreb")
            r = engine.calculate(emp)

            # Svaki iznos mora imati max 2 decimale
            for field_name in ["mio_stup_1", "mio_stup_2", "dohodak", "osobni_odbitak",
                               "porezna_osnovica", "porez", "prirez", "neto_placa",
                               "zdravstveno", "ukupni_trosak_poslodavca"]:
                value = getattr(r, field_name)
                # Provjera: round(value, 2) == value
                assert round(value, 2) == value, \
                    f"PRECISION ERROR! {field_name}={value} za bruto={bruto}"


# ═════════════════════════════════════════════════════════════
# I. SILICON / KNOWLEDGE VAULT — OČUVANJE ZNANJA
# ═════════════════════════════════════════════════════════════

class TestKnowledgeVaultIntegrity:
    """Verifikacija da Knowledge Vault pravilno čuva znanje pri zamjeni modela."""

    def test_knowledge_paths_defined(self):
        """Svih 10 knowledge pathova mora biti definirano."""
        from nyx_light.silicon.knowledge_vault import KNOWLEDGE_PATHS
        assert len(KNOWLEDGE_PATHS) >= 10

    def test_lora_compatibility_check(self):
        """LoRA kompatibilnost: isti arch → COMPATIBLE, različit → RETRAIN."""
        from nyx_light.silicon.knowledge_vault import KnowledgeVault, LoRACompatibility
        vault = KnowledgeVault()
        result = vault.check_lora_compatibility("new_model", "qwen3_235b")
        assert result in [
            LoRACompatibility.NO_ADAPTERS,
            LoRACompatibility.COMPATIBLE,
            LoRACompatibility.RETRAIN_NEEDED,
        ]

    def test_integrity_manifest_creation(self):
        """Integrity manifest mora sadržavati SHA-256 hasheve."""
        from nyx_light.silicon.knowledge_vault import KnowledgeVault
        vault = KnowledgeVault()
        manifest = vault.create_manifest()
        assert manifest.manifest_id  # Non-empty
        assert isinstance(manifest.file_hashes, dict)
        assert manifest.total_files >= 0

    def test_memory_verification(self):
        """verify_memory_intact() mora dati izvještaj o svim slojevima."""
        from nyx_light.silicon.knowledge_vault import KnowledgeVault
        vault = KnowledgeVault()
        report = vault.verify_memory_intact()
        assert "overall" in report
        assert report["overall"] in ("INTACT", "DEGRADED", "EMPTY")

    def test_swap_phases_defined(self):
        """Safe swap ima svih 10 faza."""
        from nyx_light.silicon.knowledge_vault import SwapPhase
        phases = list(SwapPhase)
        assert len(phases) >= 10


# ═════════════════════════════════════════════════════════════
# J. SILICON / HARDWARE DETECTION
# ═════════════════════════════════════════════════════════════

class TestSiliconDetection:
    """Hardware detection i UMA controller."""

    def test_detect_hardware(self):
        """detect_hardware() mora raditi na svim platformama (graceful fallback)."""
        from nyx_light.silicon.apple_silicon import detect_hardware
        hw = detect_hardware()
        assert hw.total_memory_gb > 0
        # Na Linuxu cpu_cores može biti 0 ako nije Apple Silicon
        # Ali hardware objekt mora postojati
        assert hw.chip_name  # Non-empty string

    def test_uma_controller_budgets(self):
        """UMA budgets moraju zbrojiti < 100%."""
        from nyx_light.silicon.apple_silicon import UMAController
        uma = UMAController(total_gb=256.0)
        total = sum(uma._budgets.values())
        assert total <= 1.0, f"UMA budgets ukupno {total} > 1.0!"

    def test_memory_pressure_levels(self):
        """Memory pressure leveli moraju biti definirani."""
        from nyx_light.silicon.apple_silicon import PressureLevel
        levels = list(PressureLevel)
        assert len(levels) >= 4  # NOMINAL, ELEVATED, WARNING, CRITICAL

    def test_thermal_states(self):
        """Thermal states moraju biti definirani."""
        from nyx_light.silicon.apple_silicon import ThermalState
        states = list(ThermalState)
        assert len(states) >= 4  # COOL, NOMINAL, WARM, HOT

    def test_adaptive_batch_scaling(self):
        """Batch size se smanjuje pod pritiskom — deterministički, ne AI."""
        from nyx_light.silicon.apple_silicon import (
            AdaptiveBatchController, PressureLevel, ThermalState
        )

        # Separate controllers to avoid shared state
        bc1 = AdaptiveBatchController()
        bc2 = AdaptiveBatchController()

        nominal = bc1.compute(PressureLevel.NOMINAL, ThermalState.NOMINAL)
        nominal_batch = nominal.current_batch_size
        nominal_tokens = nominal.current_max_tokens

        critical = bc2.compute(PressureLevel.CRITICAL, ThermalState.NOMINAL)
        critical_batch = critical.current_batch_size
        critical_tokens = critical.current_max_tokens

        assert nominal_batch > critical_batch, \
            f"Batch mora biti MANJI pod CRITICAL ({critical_batch}) nego NOMINAL ({nominal_batch})!"
        assert nominal_tokens > critical_tokens, \
            f"Max tokens mora biti MANJI pod CRITICAL ({critical_tokens}) nego NOMINAL ({nominal_tokens})!"


# ═════════════════════════════════════════════════════════════
# K. VLLM-MLX ENGINE
# ═════════════════════════════════════════════════════════════

class TestVLLMMLXEngine:
    """vLLM-MLX engine konfiguracija."""

    def test_config_defaults(self):
        """Defaultna konfiguracija za 15 korisnika."""
        from nyx_light.silicon.vllm_mlx_engine import VLLMMLXConfig
        config = VLLMMLXConfig()
        assert config.vllm_max_concurrency == 15
        assert config.kv_bits == 4  # 4-bit KV quantization
        assert config.enable_prompt_cache is True
        assert config.wired_kv_cache is True  # Prevent page-out

    def test_prompt_cache(self):
        """Prompt cache mora cachirati system prompt KV state."""
        from nyx_light.silicon.vllm_mlx_engine import PromptCache
        cache = PromptCache()

        # Put
        cache.put("test_prompt", {"kv": "state"})
        # Get
        result = cache.get("test_prompt")
        assert result is not None
        assert result["kv"] == "state"

        # Miss
        assert cache.get("nonexistent") is None

        # Hit rate
        assert cache.hit_rate > 0


# ═════════════════════════════════════════════════════════════
# L. MATH VS AI SEPARATION SUMMARY
# ═════════════════════════════════════════════════════════════

class TestMathVsAISeparation:
    """
    FINALNI META-TEST: Dokumentira koji modul koristi math a koji AI.
    
    ┌──────────────────────────┬───────────┬──────────────────────────────────┐
    │ Modul                    │ Tip       │ Što radi                         │
    ├──────────────────────────┼───────────┼──────────────────────────────────┤
    │ Payroll (bruto→neto)     │ MATH ✅   │ MIO, porez, prirez, neto         │
    │ PDV Prijava              │ MATH ✅   │ Obveza, pretporez, razlika       │
    │ Amortizacija             │ MATH ✅   │ Stopa × nabavna / 12             │
    │ Porez na dobit           │ MATH ✅   │ Osnovica, stopa, porez           │
    │ Putni nalozi             │ MATH ✅   │ Km naknada, dnevnice, 50% repr.  │
    │ Blagajna                 │ MATH ✅   │ AML limit, stanje blagajne       │
    │ Ugovor o djelu           │ MATH ✅   │ Doprinosi, porez, neto           │
    │ Autorski honorar         │ MATH ✅   │ Normirani trošak, doprinosi      │
    │ Kontiranje               │ AI 🤖    │ Prijedlog konta (NE iznos!)      │
    │ Invoice OCR              │ AI 🤖    │ Čitanje skenova (Vision model)   │
    │ Report Explanation       │ AI 🤖    │ Objašnjenje bilanci na HR        │
    │ Business Plan            │ AI 🤖    │ Generiranje teksta plana         │
    │ Client Onboarding        │ AI 🤖    │ Validacija OIB-a, NLP            │
    │ Mgmt Accounting          │ HYBRID ⚡ │ AI analiza + MATH izračun        │
    └──────────────────────────┴───────────┴──────────────────────────────────┘
    
    PRAVILO: AI NIKADA ne generira financijski iznos.
    Svi iznosi dolaze iz determinističkih formula u Python kodu.
    AI služi za: klasifikaciju, NLP, objašnjenja, prijedloge.
    """

    def test_math_modules_no_ai_dependency(self):
        """Matematički moduli ne smiju imati dependency na LLM."""
        import importlib
        math_modules = [
            "nyx_light.modules.payroll",
            "nyx_light.modules.pdv_prijava",
            "nyx_light.modules.osnovna_sredstva",
            "nyx_light.modules.porez_dobit",
            "nyx_light.modules.putni_nalozi.checker",
            "nyx_light.modules.blagajna.validator",
        ]

        for mod_name in math_modules:
            mod = importlib.import_module(mod_name)
            source_file = mod.__file__
            with open(source_file, "r") as f:
                source = f.read()

            # Ne smije importirati LLM, chat, AI
            for forbidden in ["import mlx", "from mlx", "import openai",
                              "chat_bridge", "llm_provider", "generate("]:
                assert forbidden not in source, (
                    f"HALUCINACIJA OPASNOST! {mod_name} importira '{forbidden}' — "
                    "matematički modul NE SMIJE ovisiti o AI!"
                )

    def test_ai_modules_always_require_approval(self):
        """AI moduli UVIJEK moraju imati requires_approval."""
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        engine = KontiranjeEngine()

        # Svaki AI prijedlog mora tražiti odobrenje
        test_inputs = ["Nabava materijala", "Servis", "Amortizacija", "Nepoznato XYZ"]
        for desc in test_inputs:
            result = engine.suggest_konto(desc)
            assert result["requires_approval"] is True, \
                f"AI prijedlog za '{desc}' NEMA requires_approval!"


# ═════════════════════════════════════════════════════════════
# POKRETANJE
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-x"])
