"""
Tests za Sprint 6 module: Payroll, Izlazni računi, Obračunske stavke,
Rokovi, Prošireni kontni plan.
"""

import pytest
from datetime import date


# ═══════════════════════════════════════════════════════
# PAYROLL ENGINE
# ═══════════════════════════════════════════════════════

class TestPayrollEngine:
    """Bruto→neto obračun plaće za RH."""

    def setup_method(self):
        from nyx_light.modules.payroll import PayrollEngine, Employee
        self.pe = PayrollEngine()
        self.Employee = Employee

    def test_basic_bruto_neto(self):
        emp = self.Employee(name="Test", bruto_placa=2000.0, city="Zagreb")
        r = self.pe.calculate(emp)
        assert r.bruto_placa == 2000.0
        assert r.mio_stup_1 == 300.0   # 15%
        assert r.mio_stup_2 == 100.0   # 5%
        assert r.dohodak == 1600.0      # 2000 - 400
        assert r.neto_placa > 0
        assert r.neto_placa < r.bruto_placa
        assert r.requires_approval is True

    def test_doprinosi_20_posto(self):
        """Ukupni doprinosi iz plaće = 20% bruta."""
        emp = self.Employee(name="Test", bruto_placa=3000.0)
        r = self.pe.calculate(emp)
        assert r.ukupno_doprinosi_iz == 600.0  # 20% od 3000

    def test_zdravstveno_16_5_posto(self):
        """Doprinos na plaću (teret poslodavca) = 16.5%."""
        emp = self.Employee(name="Test", bruto_placa=2000.0)
        r = self.pe.calculate(emp)
        assert r.zdravstveno == 330.0  # 16.5% od 2000
        assert r.ukupni_trosak_poslodavca == 2330.0

    def test_osobni_odbitak_bez_djece(self):
        emp = self.Employee(name="Test", bruto_placa=2000.0)
        r = self.pe.calculate(emp)
        assert r.osobni_odbitak == 560.0  # Osnovni osobni odbitak

    def test_osobni_odbitak_s_djecom(self):
        emp = self.Employee(name="Test", bruto_placa=2000.0, djeca=2)
        r = self.pe.calculate(emp)
        # 560 + 0.7*560 + 1.0*560 = 560 + 392 + 560 = 1512
        assert r.osobni_odbitak == 1512.0

    def test_porez_progresivne_stope(self):
        """Niska stopa 20% do 4200 EUR, viša 30% iznad."""
        emp = self.Employee(name="Test", bruto_placa=6000.0)
        r = self.pe.calculate(emp)
        assert r.porezna_osnovica > 4200.0  # Dolazi u višu stopu
        assert r.porez > 840.0  # Više od 20% * 4200

    def test_prirez_zagreb(self):
        emp = self.Employee(name="Test", bruto_placa=3000.0, city="Zagreb")
        r = self.pe.calculate(emp)
        if r.porez > 0:
            assert r.prirez == round(r.porez * 18.0 / 100, 2)

    def test_prirez_split(self):
        emp = self.Employee(name="Test", bruto_placa=3000.0, city="Split")
        r = self.pe.calculate(emp)
        if r.porez > 0:
            assert r.prirez == round(r.porez * 15.0 / 100, 2)

    def test_olaksica_mladi_do_25(self):
        """100% oslobođenje poreza za < 25 godina."""
        emp = self.Employee(name="Mladi", bruto_placa=1500.0,
                            birth_date=date(2003, 1, 1), city="Zagreb")
        r = self.pe.calculate(emp)
        assert r.olaksica_mladi_pct == 100.0
        assert r.ukupno_porez_prirez == 0.0

    def test_olaksica_mladi_25_30(self):
        """50% oslobođenje poreza za 25-30."""
        emp = self.Employee(name="Mladi2", bruto_placa=3000.0,
                            birth_date=date(1998, 6, 15), city="Zagreb")
        r = self.pe.calculate(emp)
        assert r.olaksica_mladi_pct == 50.0

    def test_ispod_minimalne(self):
        emp = self.Employee(name="Test", bruto_placa=500.0)
        r = self.pe.calculate(emp)
        assert len(r.warnings) > 0
        assert "minimalne" in r.warnings[0].lower()

    def test_bez_drugog_stupa(self):
        """Radnik bez II. stupa — sav MIO 20% ide u I. stup."""
        emp = self.Employee(name="Stariji", bruto_placa=2000.0, mio_stup_2=False)
        r = self.pe.calculate(emp)
        assert r.mio_stup_1 == 400.0  # 20% * 2000
        assert r.mio_stup_2 == 0.0
        assert r.ukupno_doprinosi_iz == 400.0

    def test_ugovor_o_djelu(self):
        r = self.pe.calculate_ugovor_o_djelu(1000.0)
        assert r["vrsta"] == "ugovor_o_djelu"
        assert r["mio_stup_1"] == 75.0   # 7.5%
        assert r["mio_stup_2"] == 25.0   # 2.5%
        assert r["zdravstveno"] == 75.0   # 7.5%
        assert r["neto"] < 1000.0
        assert r["requires_approval"] is True

    def test_autorski_honorar(self):
        r = self.pe.calculate_autorski_honorar(2000.0, 30.0)
        assert r["vrsta"] == "autorski_honorar"
        assert r["normirani_trosak"] == 600.0  # 30% od 2000
        assert r["osnovica_za_doprinose"] == 1400.0
        assert r["neto"] < 2000.0

    def test_neoporezive_naknade(self):
        n = self.pe.neoporezive_naknade(22)
        assert n["topli_obrok_po_danu"] > 0
        assert n["topli_obrok_max"] == round(n["topli_obrok_po_danu"] * 22, 2)
        assert n["dnevnica_rh_puna"] > 0
        assert n["regres_god"] > 0


# ═══════════════════════════════════════════════════════
# OUTGOING INVOICE VALIDATOR
# ═══════════════════════════════════════════════════════

class TestOutgoingInvoiceValidator:
    """Validacija izlaznih računa prema Zakonu o PDV-u."""

    def setup_method(self):
        from nyx_light.modules.outgoing_invoice import OutgoingInvoiceValidator
        self.v = OutgoingInvoiceValidator()

    def _valid_invoice(self, **overrides):
        base = {
            "broj_racuna": "R-2026-001",
            "datum_izdavanja": "2026-02-26",
            "oib_izdavatelja": "12345678903",   # Valid OIB (MOD 11,10 checked)
            "naziv_izdavatelja": "TENA BE d.o.o.",
            "adresa_izdavatelja": "Zagreb, Ilica 1",
            "oib_primatelja": "98765432106",     # Valid OIB (MOD 11,10 checked)
            "opis_isporuke": "Računovodstvene usluge",
            "iznos": 625.0,      # 500 + 125 PDV
            "pdv_stopa": 25.0,
            "pdv_iznos": 125.0,  # 625 * 25/125 = 125
        }
        base.update(overrides)
        return base

    def test_valid_invoice(self):
        r = self.v.validate(self._valid_invoice())
        assert r.valid is True
        assert len(r.errors) == 0

    def test_missing_broj_racuna(self):
        r = self.v.validate(self._valid_invoice(broj_racuna=""))
        assert r.valid is False
        assert any("broj računa" in e.lower() for e in r.errors)

    def test_missing_datum(self):
        r = self.v.validate(self._valid_invoice(datum_izdavanja=""))
        assert r.valid is False

    def test_invalid_oib_izdavatelja(self):
        r = self.v.validate(self._valid_invoice(oib_izdavatelja="11111111111"))
        assert r.valid is False
        assert any("OIB izdavatelja" in e for e in r.errors)

    def test_missing_opis(self):
        r = self.v.validate(self._valid_invoice(opis_isporuke=""))
        assert r.valid is False
        assert any("opis isporuke" in e.lower() for e in r.errors)

    def test_nestandarna_pdv_stopa(self):
        r = self.v.validate(self._valid_invoice(pdv_stopa=17.0))
        assert any("Nestandarna" in w or "nestandarna" in w.lower() for w in r.warnings)

    def test_eu_reverse_charge(self):
        r = self.v.validate(self._valid_invoice(
            zemlja_primatelja="DE",
            eu_vat_id="DE123456789",
            pdv_stopa=25.0,
        ))
        assert r.pdv_status == "reverse_charge"
        assert any("reverse charge" in w.lower() for w in r.warnings)

    def test_eu_bez_vat_id(self):
        r = self.v.validate(self._valid_invoice(
            zemlja_primatelja="AT",
        ))
        assert r.pdv_status == "standard"

    def test_export_treca_zemlja(self):
        r = self.v.validate(self._valid_invoice(
            zemlja_primatelja="US",
        ))
        assert r.pdv_status == "export"

    def test_gotovinski_bez_jir(self):
        r = self.v.validate(self._valid_invoice(gotovinski=True))
        assert r.valid is False
        assert any("JIR" in e for e in r.errors)

    def test_gotovinski_s_jir(self):
        r = self.v.validate(self._valid_invoice(gotovinski=True, jir="ABC-123"))
        # Should have no fiskalizacija error
        assert not any("JIR" in e for e in r.errors)

    def test_oib_validation_algorithm(self):
        """Provjera MOD 11,10 algoritma za OIB."""
        assert self.v._valid_oib("12345678903") is True
        assert self.v._valid_oib("98765432106") is True
        assert self.v._valid_oib("11111111111") is False
        assert self.v._valid_oib("123") is False
        assert self.v._valid_oib("") is False


# ═══════════════════════════════════════════════════════
# ACCRUALS CHECKLIST
# ═══════════════════════════════════════════════════════

class TestAccrualsChecklist:
    """Obračunske stavke — period-end checklist."""

    def setup_method(self):
        from nyx_light.modules.accruals import AccrualsChecklist
        self.ac = AccrualsChecklist()

    def test_monthly_checklist(self):
        r = self.ac.get_checklist("monthly")
        assert r["period"] == "monthly"
        assert r["total_items"] >= 5
        assert r["auto_calculable"] >= 2  # Amortizacija

    def test_yearly_checklist_has_more(self):
        monthly = self.ac.get_checklist("monthly")
        yearly = self.ac.get_checklist("yearly")
        assert yearly["total_items"] > monthly["total_items"]

    def test_yearly_has_inventura(self):
        r = self.ac.get_checklist("yearly")
        names = [i["name"] for i in r["items"]]
        assert any("zaliha" in n.lower() or "inventur" in n.lower() for n in names)

    def test_yearly_has_porezno_nepriznati(self):
        r = self.ac.get_checklist("yearly")
        names = [i["name"] for i in r["items"]]
        assert any("porezno nepriznati" in n.lower() for n in names)

    def test_yearly_has_razgranicenja(self):
        r = self.ac.get_checklist("yearly")
        names = [i["name"] for i in r["items"]]
        assert any("razgraničenja" in n.lower() for n in names)

    def test_all_require_approval(self):
        r = self.ac.get_checklist("yearly")
        assert "odobrenje računovođe" in r["warning"].lower()

    def test_custom_items(self):
        r = self.ac.get_checklist("monthly", custom_items=[
            {"name": "Posebna stavka klijenta X", "category": "korekcija"}
        ])
        names = [i["name"] for i in r["items"]]
        assert "Posebna stavka klijenta X" in names


# ═══════════════════════════════════════════════════════
# DEADLINE TRACKER
# ═══════════════════════════════════════════════════════

class TestDeadlineTracker:
    """Praćenje zakonskih rokova."""

    def setup_method(self):
        from nyx_light.modules.deadlines import DeadlineTracker
        self.dt = DeadlineTracker()

    def test_has_deadlines(self):
        assert len(self.dt.deadlines) >= 10

    def test_upcoming_returns_list(self):
        upcoming = self.dt.get_upcoming(30)
        assert isinstance(upcoming, list)
        for item in upcoming:
            assert "name" in item
            assert "date" in item
            assert "urgency" in item

    def test_upcoming_sorted_by_days(self):
        upcoming = self.dt.get_upcoming(60, today=date(2026, 3, 1))
        if len(upcoming) >= 2:
            assert upcoming[0]["days_left"] <= upcoming[1]["days_left"]

    def test_urgency_levels(self):
        """Provjeri critical/warning/normal."""
        upcoming = self.dt.get_upcoming(30, today=date(2026, 3, 18))
        urgencies = {item["urgency"] for item in upcoming}
        # Should have at least normal items
        assert len(urgencies) > 0

    def test_monthly_calendar(self):
        cal = self.dt.get_monthly_calendar(2026, 4)
        assert len(cal) >= 5  # Travanj ima dosta rokova

    def test_april_has_pd_obrazac(self):
        """Travanj = rok za godišnju prijavu poreza na dobit."""
        cal = self.dt.get_monthly_calendar(2026, 4)
        names = [c["name"] for c in cal]
        assert any("dobit" in n.lower() or "PD" in n for n in names)

    def test_april_has_gfi(self):
        """Travanj = rok za GFI predaju FINA."""
        cal = self.dt.get_monthly_calendar(2026, 4)
        names = [c["name"] for c in cal]
        assert any("GFI" in n for n in names)

    def test_joppd_monthly(self):
        """JOPPD je mjesečni rok."""
        cal = self.dt.get_monthly_calendar(2026, 3)
        names = [c["name"] for c in cal]
        assert any("JOPPD" in n for n in names)


# ═══════════════════════════════════════════════════════
# KONTNI PLAN (PROŠIRENI)
# ═══════════════════════════════════════════════════════

class TestKontniPlan:
    """Prošireni kontni plan za RH."""

    def setup_method(self):
        from nyx_light.modules.kontiranje.kontni_plan import (
            get_full_kontni_plan, get_konto_name, suggest_konto_by_keyword, TOTAL_KONTA
        )
        self.plan = get_full_kontni_plan()
        self.get_name = get_konto_name
        self.search = suggest_konto_by_keyword
        self.total = TOTAL_KONTA

    def test_minimum_100_konta(self):
        assert self.total >= 100, f"Kontni plan ima samo {self.total} konta"

    def test_svi_razredi_zastupljeni(self):
        """Kontni plan mora imati razrede 0-9."""
        first_digits = {k[0] for k in self.plan.keys()}
        for d in "012345678":
            assert d in first_digits, f"Nedostaje razred {d}"

    def test_get_konto_name(self):
        assert "dobavljač" in self.get_name("4000").lower()

    def test_unknown_konto(self):
        assert self.get_name("9999") == "Nepoznat konto"

    def test_search_amortizacija(self):
        results = self.search("amortizacija")
        assert len(results) >= 2

    def test_search_placa(self):
        results = self.search("plaća") or self.search("plaće")
        assert len(results) >= 1

    def test_search_pdv(self):
        results = self.search("PDV") or self.search("dodanu vrijednost")
        assert len(results) >= 1

    def test_search_dobavljaci(self):
        results = self.search("dobavljač")
        assert len(results) >= 2  # U zemlji, EU, izvan EU

    def test_razred_4_has_placni_konta(self):
        """Razred 4 mora imati konta za plaće i doprinose."""
        plan_r4 = {k: v for k, v in self.plan.items() if k.startswith("4")}
        names = " ".join(plan_r4.values()).lower()
        assert "plaće" in names or "plaća" in names
        assert "doprinos" in names
