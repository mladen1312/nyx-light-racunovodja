"""
Sprint 7 E2E: NyxLightApp kostur — svaki modul → CPP/Synesis.

Ovo testira KOMPLETNI TOK od dokumenta do ERP exporta.
"""
import pytest
from datetime import date


class TestNyxLightAppSkeleton:
    """Testira NyxLightApp — centralni kostur sustava."""

    def setup_method(self):
        from nyx_light.app import NyxLightApp
        from nyx_light.registry import ClientConfig
        self.app = NyxLightApp(export_dir="/tmp/nyx_e2e_test")
        self.ClientConfig = ClientConfig

        # Registriraj test klijente
        self.app.register_client(ClientConfig(
            id="CPP-001", naziv="ABC d.o.o.", oib="12345678903",
            erp_target="CPP", erp_export_format="XML",
            pdv_period="monthly", kategorija="mali",
        ))
        self.app.register_client(ClientConfig(
            id="SYN-001", naziv="XYZ j.d.o.o.", oib="98765432106",
            erp_target="Synesis", erp_export_format="CSV",
            pdv_period="quarterly", kategorija="mikro",
        ))

    # ── A1: Ulazni račun → CPP ──

    def test_invoice_to_cpp(self):
        result = self.app.process_invoice({
            "iznos": 1250.0, "pdv_iznos": 250.0, "pdv_stopa": 25,
            "dobavljac": "HEP d.d.", "oib": "46830600751",
            "broj_racuna": "R-2026-567", "datum": "2026-02-26",
        }, client_id="CPP-001")

        assert result["status"] == "pending"
        pid = result["id"]

        self.app.approve(pid, "ana")
        export = self.app.export_to_erp("CPP-001")
        assert export["status"] == "exported"
        assert export["erp"] == "CPP"
        assert export["format"] == "XML"

    # ── A1: Ulazni račun → Synesis ──

    def test_invoice_to_synesis(self):
        result = self.app.process_invoice({
            "iznos": 500.0, "pdv_iznos": 100.0, "pdv_stopa": 25,
            "dobavljac": "HT d.d.", "datum": "2026-02-26",
        }, client_id="SYN-001")

        pid = result["id"]
        self.app.approve(pid, "marko")
        export = self.app.export_to_erp("SYN-001")
        assert export["status"] == "exported"
        assert export["erp"] == "Synesis"
        assert export["format"] == "CSV"

    # ── A2: Izlazni račun validacija ──

    def test_outgoing_invoice_validation(self):
        result = self.app.validate_outgoing_invoice({
            "broj_racuna": "IR-2026-001", "datum_izdavanja": "2026-02-26",
            "oib_izdavatelja": "12345678903", "naziv_izdavatelja": "ABC d.o.o.",
            "adresa_izdavatelja": "Zagreb", "oib_primatelja": "98765432106",
            "opis_isporuke": "Usluge", "iznos": 625.0,
            "pdv_stopa": 25.0, "pdv_iznos": 125.0,
        })
        assert result["valid"] is True

    # ── A5: Blagajna → CPP ──

    def test_petty_cash_to_cpp(self):
        result = self.app.process_petty_cash({
            "iznos": 50.0, "vrsta": "isplata", "opis": "Uredski materijal",
            "datum": "2026-02-26",
        }, client_id="CPP-001")
        assert result["status"] == "pending"

    def test_petty_cash_aml_block(self):
        result = self.app.process_petty_cash({
            "iznos": 15000.0, "vrsta": "isplata", "opis": "Veliko plaćanje",
        }, client_id="CPP-001")
        assert result["status"] == "rejected"

    # ── A6: Putni nalog → Synesis ──

    def test_travel_expense_to_synesis(self):
        result = self.app.process_travel_expense({
            "km": 200, "dnevnica": 26.55, "ostali_troskovi": 50,
            "djelatnik": "Ana H.", "odrediste": "Split",
        }, client_id="SYN-001")
        assert result["status"] == "pending"

    # ── A7: Osnovna sredstva ──

    def test_fixed_asset_depreciation_to_cpp(self):
        self.app.add_fixed_asset({
            "naziv": "Laptop", "vrsta": "računalna_oprema",
            "nabavna_vrijednost": 1200.0,
        })
        result = self.app.run_monthly_depreciation("CPP-001")
        assert result["submitted"] == 1

    def test_sitan_inventar_not_depreciated(self):
        r = self.app.add_fixed_asset({"naziv": "Miš", "nabavna_vrijednost": 30.0})
        assert r["status"] == "sitan_inventar"

    # ── A8: Obračunske stavke ──

    def test_accruals_checklist(self):
        cl = self.app.get_period_checklist("yearly", "CPP-001")
        assert cl["total_items"] >= 10

    # ── A9: IOS → CPP ──

    def test_ios_to_cpp(self):
        result = self.app.process_ios({
            "razlika": -200, "partner": "Partner d.o.o.",
            "oib": "12345678903",
        }, client_id="CPP-001")
        assert result["status"] == "pending"

    # ── B: Plaće → CPP + JOPPD ──

    def test_payroll_to_cpp_with_joppd(self):
        from nyx_light.modules.payroll import Employee

        employees = [
            Employee(name="Ana H.", bruto_placa=2000, city="Zagreb",
                     djeca=1, birth_date=date(1990, 5, 15)),
            Employee(name="Luka M.", bruto_placa=1500, city="Zagreb",
                     birth_date=date(2002, 3, 10)),  # Mladi <25
        ]
        result = self.app.process_payroll(employees, "CPP-001")

        assert result["submitted"] == 2
        assert result["joppd"] is not None
        assert result["joppd"]["ukupno"]["bruto"] == 3500.0
        assert result["joppd"]["requires_approval"] is True

        # Approve both
        self.app.approve_batch(result["ids"], "ana")
        export = self.app.export_to_erp("CPP-001")
        assert export["proposals_exported"] >= 2

    # ── C: PDV prijava ──

    def test_pdv_prijava(self):
        from nyx_light.modules.pdv_prijava import PDVStavka

        stavke = [
            PDVStavka(tip="izlazni", osnovica=1000, pdv_stopa=25, pdv_iznos=250),
            PDVStavka(tip="izlazni", osnovica=500, pdv_stopa=13, pdv_iznos=65),
            PDVStavka(tip="ulazni", osnovica=800, pdv_stopa=25, pdv_iznos=200),
        ]
        result = self.app.prepare_pdv_prijava(stavke, "CPP-001")
        assert result["ukupna_obveza"] == 315.0  # 250 + 65
        assert result["ukupni_pretporez"] == 200.0
        assert result["za_uplatu"] == 115.0      # 315 - 200

    # ── D: GFI priprema ──

    def test_gfi_preparation(self):
        result = self.app.prepare_gfi("CPP-001", 2025)
        assert "checklist" in result
        assert "bilanca" in result
        assert "rdg" in result

    # ── F: Rokovi ──

    def test_upcoming_deadlines(self):
        deadlines = self.app.get_upcoming_deadlines(30)
        assert isinstance(deadlines, list)

    # ── Kontni plan ──

    def test_search_konto(self):
        results = self.app.search_konto("amortizacija")
        assert len(results) >= 2

    # ── System status ──

    def test_system_status(self):
        status = self.app.get_system_status()
        assert "pipeline" in status
        assert "clients" in status
        assert "modules" in status
        assert status["kontni_plan_konta"] >= 100

    # ── Client registry ──

    def test_client_registry_erp_routing(self):
        assert self.app.get_client_erp("CPP-001") == "CPP"
        assert self.app.get_client_erp("SYN-001") == "Synesis"
        assert self.app.get_client_erp("UNKNOWN") == "CPP"  # Default

    # ── FULL LIFECYCLE: Multiple docs → batch approve → export ──

    def test_full_lifecycle_mixed_documents(self):
        """
        Simulacija realnog rada:
        1. Ulazni račun
        2. Blagajna
        3. Putni nalog
        Sve odobri → export → CPP
        """
        ids = []

        # Račun
        r1 = self.app.process_invoice(
            {"iznos": 625, "pdv_iznos": 125, "pdv_stopa": 25,
             "dobavljac": "HEP", "datum": "2026-02-26"},
            "CPP-001",
        )
        ids.append(r1["id"])

        # Blagajna
        r2 = self.app.process_petty_cash(
            {"iznos": 30, "vrsta": "isplata", "opis": "Pošta"},
            "CPP-001",
        )
        ids.append(r2["id"])

        # Putni nalog
        r3 = self.app.process_travel_expense(
            {"km": 100, "dnevnica": 26.55, "djelatnik": "Ana", "odrediste": "Zadar"},
            "CPP-001",
        )
        ids.append(r3["id"])

        assert len(self.app.get_pending("CPP-001")) == 3

        # Batch approve
        self.app.approve_batch(ids, "ana")
        assert len(self.app.get_pending("CPP-001")) == 0
        assert len(self.app.get_approved("CPP-001")) == 3

        # Export
        export = self.app.export_to_erp("CPP-001")
        assert export["proposals_exported"] == 3
        assert export["status"] == "exported"


class TestPDVPrijavaModule:
    """Posebni testovi za PDV prijavu."""

    def setup_method(self):
        from nyx_light.modules.pdv_prijava import PDVPrijavaEngine, PDVStavka
        self.engine = PDVPrijavaEngine()
        self.PDVStavka = PDVStavka

    def test_basic_calculation(self):
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=10000, pdv_stopa=25, pdv_iznos=2500),
            self.PDVStavka(tip="ulazni", osnovica=8000, pdv_stopa=25, pdv_iznos=2000),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.ukupna_obveza == 2500
        assert ppo.ukupni_pretporez == 2000
        assert ppo.za_uplatu == 500

    def test_pretporez_veci(self):
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=1000, pdv_stopa=25, pdv_iznos=250),
            self.PDVStavka(tip="ulazni", osnovica=5000, pdv_stopa=25, pdv_iznos=1250),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.za_povrat == 1000  # 1250 - 250

    def test_eu_reverse_charge(self):
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=5000, eu_transakcija=True,
                          reverse_charge=True, zemlja="DE"),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.eu_isporuke_osnovica == 5000
        assert ppo.izlazni_25_pdv == 0  # Reverse charge — bez PDV-a

    def test_ec_sales_list(self):
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=3000, eu_transakcija=True,
                          oib_partnera="DE123", naziv_partnera="Berlin GmbH",
                          zemlja="DE", kategorija="usluga"),
            self.PDVStavka(tip="izlazni", osnovica=2000, eu_transakcija=True,
                          oib_partnera="AT456", naziv_partnera="Wien AG",
                          zemlja="AT", kategorija="roba"),
        ]
        ecsl = self.engine.ec_sales_list(stavke)
        assert len(ecsl) == 2

    def test_multiple_rates(self):
        stavke = [
            self.PDVStavka(tip="izlazni", osnovica=1000, pdv_stopa=25, pdv_iznos=250),
            self.PDVStavka(tip="izlazni", osnovica=500, pdv_stopa=13, pdv_iznos=65),
            self.PDVStavka(tip="izlazni", osnovica=200, pdv_stopa=5, pdv_iznos=10),
        ]
        ppo = self.engine.calculate(stavke)
        assert ppo.izlazni_25_pdv == 250
        assert ppo.izlazni_13_pdv == 65
        assert ppo.izlazni_5_pdv == 10


class TestEnhancedBlagajna:
    """Testovi za Enhanced Blagajna V2."""

    def setup_method(self):
        from nyx_light.modules.blagajna.validator import BlagajnaValidator, BlagajnaTx
        self.v = BlagajnaValidator()
        self.Tx = BlagajnaTx

    def test_aml_block(self):
        tx = self.Tx(iznos=15000, vrsta="isplata")
        r = self.v.validate_transaction(tx)
        assert r.valid is False
        assert any("ZABRANA" in e for e in r.errors)

    def test_negative_balance(self):
        tx = self.Tx(iznos=500, vrsta="isplata")
        r = self.v.validate_transaction(tx, current_balance=100)
        assert r.valid is False

    def test_sequential_gap(self):
        self.v._zadnji_rb = 5
        tx = self.Tx(redni_broj=8, iznos=50, vrsta="uplata")
        r = self.v.validate_transaction(tx, current_balance=100)
        assert any("Praznina" in w for w in r.warnings)

    def test_over_max_balance(self):
        tx = self.Tx(iznos=9000, vrsta="uplata")
        r = self.v.validate_transaction(tx, current_balance=5000)
        assert any("max" in w.lower() for w in r.warnings)

    def test_legacy_api(self):
        r = self.v.validate(iznos=50, tip="isplata")
        assert "valid" in r


class TestEnhancedPutniNalozi:
    """Testovi za Enhanced Putni nalozi V2."""

    def setup_method(self):
        from nyx_light.modules.putni_nalozi.checker import PutniNalogChecker, PutniNalog
        self.c = PutniNalogChecker()
        self.PN = PutniNalog

    def test_km_over_limit(self):
        pn = self.PN(djelatnik="Ana", km=100, km_naknada=0.50, datum_od="2026-02-26")
        r = self.c.validate_full(pn)
        assert any("0.30" in w for w in r.warnings)

    def test_reprezentacija_50pct(self):
        pn = self.PN(djelatnik="Ana", reprezentacija=200.0, datum_od="2026-02-26")
        r = self.c.validate_full(pn)
        assert r.ukupno_porezno_nepriznato == 100.0  # 50% of 200

    def test_missing_djelatnik(self):
        pn = self.PN(km=100)
        r = self.c.validate_full(pn)
        assert r.valid is False

    def test_totals(self):
        pn = self.PN(djelatnik="Ana", km=100, dnevnica=26.55,
                     cestarina=15, parking=5, datum_od="2026-02-26")
        r = self.c.validate_full(pn)
        assert r.km_naknada_ukupno == 30.0  # 100 * 0.30
        assert r.ukupno == 30.0 + 26.55 + 15 + 5

    def test_legacy_api(self):
        r = self.c.validate(km=100)
        assert "naknada_ukupno" in r
