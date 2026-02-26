"""
Sprint 7 Tests: Unified Pipeline, JOPPD, GFI, Osnovna sredstva,
e-Računi/Pantheon parseri, full E2E flow to CPP/Synesis.
"""

import pytest
from datetime import date


# ═══════════════════════════════════════════════════════
# UNIFIED BOOKING PIPELINE — KOSTUR
# ═══════════════════════════════════════════════════════

class TestBookingPipeline:
    """Test centralnog pipeline-a: Modul → Prijedlog → Odobrenje → Export."""

    def setup_method(self):
        from nyx_light.pipeline import BookingPipeline, BookingProposal
        self.pipeline = BookingPipeline()
        self.BookingProposal = BookingProposal

    def _make_proposal(self, **kwargs):
        defaults = {
            "client_id": "KLIJENT-001",
            "document_type": "ulazni_racun",
            "erp_target": "CPP",
            "ukupni_iznos": 1000.0,
            "opis": "Test knjiženje",
            "confidence": 0.85,
            "source_module": "test",
            "lines": [
                {"konto": "7200", "strana": "duguje", "iznos": 800.0, "opis": "Usluga"},
                {"konto": "1230", "strana": "duguje", "iznos": 200.0, "opis": "Pretporez"},
                {"konto": "4000", "strana": "potrazuje", "iznos": 1000.0, "opis": "Dobavljač"},
            ],
        }
        defaults.update(kwargs)
        return self.BookingProposal(**defaults)

    def test_submit_proposal(self):
        p = self._make_proposal()
        result = self.pipeline.submit(p)
        assert result["status"] == "pending"
        assert result["requires_approval"] is True
        assert result["iznos"] == 1000.0

    def test_approve_proposal(self):
        p = self._make_proposal()
        self.pipeline.submit(p)
        result = self.pipeline.approve(p.id, "racunovoda_1")
        assert result["status"] == "approved"
        assert result["ready_for_export"] is True

    def test_reject_proposal(self):
        p = self._make_proposal()
        self.pipeline.submit(p)
        result = self.pipeline.reject(p.id, "racunovoda_1", "Krivi konto")
        assert result["status"] == "rejected"

    def test_correct_proposal(self):
        p = self._make_proposal()
        self.pipeline.submit(p)
        result = self.pipeline.correct(p.id, "racunovoda_1", {"opis": "Ispravljen opis"})
        assert result["status"] == "corrected"
        assert result["ready_for_export"] is True
        assert "DPO" in result["note"]

    def test_export_requires_approval(self):
        """Export ne radi bez odobrenja — TVRDA GRANICA."""
        p = self._make_proposal()
        self.pipeline.submit(p)
        # Pokušaj export bez odobrenja
        result = self.pipeline.export_approved(client_id="KLIJENT-001")
        assert result["status"] == "empty"  # Nema odobrenih

    def test_full_flow_submit_approve_export(self):
        """E2E: Submit → Approve → Export."""
        p = self._make_proposal()
        self.pipeline.submit(p)
        self.pipeline.approve(p.id, "racunovoda_1")
        result = self.pipeline.export_approved(client_id="KLIJENT-001")
        assert result["proposals_exported"] == 1
        assert result["booking_lines"] == 3  # 3 stavke

    def test_batch_submit(self):
        proposals = [self._make_proposal() for _ in range(5)]
        result = self.pipeline.submit_batch(proposals)
        assert result["batch_size"] == 5
        assert result["submitted"] == 5

    def test_get_pending(self):
        p = self._make_proposal()
        self.pipeline.submit(p)
        pending = self.pipeline.get_pending()
        assert len(pending) == 1
        assert pending[0]["iznos"] == 1000.0

    def test_stats(self):
        p = self._make_proposal()
        self.pipeline.submit(p)
        stats = self.pipeline.get_stats()
        assert stats["received"] == 1
        assert stats["pending"] == 1

    # ── MODUL-SPECIFIČNE PRETVORBE ──

    def test_from_invoice(self):
        invoice = {
            "iznos": 1250.0, "pdv_iznos": 250.0, "pdv_stopa": 25,
            "dobavljac": "HEP d.d.", "oib": "46830600751",
            "broj_racuna": "R-2026-001", "datum": "2026-02-26",
        }
        kontiranje = {"suggested_konto": "5020", "confidence": 0.9}
        p = self.pipeline.from_invoice(invoice, kontiranje, "K001")
        assert p.document_type == "ulazni_racun"
        assert len(p.lines) == 3  # Trošak + Pretporez + Dobavljač
        assert p.lines[0]["konto"] == "5020"
        assert p.lines[1]["konto"] == "1230"  # Pretporez
        assert p.lines[2]["konto"] == "4000"  # Dobavljač

    def test_from_bank_statement(self):
        txs = [
            {"direction": "out", "amount": 500, "suggested_konto": "4000",
             "opis": "Plaćanje dobavljaču", "partner": "HT d.d."},
            {"direction": "in", "amount": 1200, "suggested_konto": "1200",
             "opis": "Naplata kupca", "partner": "ABC d.o.o."},
        ]
        proposals = self.pipeline.from_bank_statement(txs, "K001")
        assert len(proposals) == 2
        assert proposals[0].document_type == "bankovni_izvod"
        # Isplata: duguje dobavljač, potražuje žiro
        assert proposals[0].lines[1]["konto"] == "1500"
        # Uplata: duguje žiro, potražuje kupac
        assert proposals[1].lines[0]["konto"] == "1500"

    def test_from_payroll(self):
        from nyx_light.modules.payroll import PayrollEngine, Employee
        pe = PayrollEngine()
        emp = Employee(name="Test", bruto_placa=2000.0, city="Zagreb")
        pr = pe.calculate(emp)
        p = self.pipeline.from_payroll(pr, "K001")
        assert p.document_type == "placa"
        assert any(l["konto"] == "5200" for l in p.lines)  # Trošak plaće
        assert any(l["konto"] == "4200" for l in p.lines)  # Neto za isplatu
        assert any(l["konto"] == "4210" for l in p.lines)  # MIO I

    def test_from_petty_cash(self):
        p = self.pipeline.from_petty_cash(
            {"iznos": 50, "vrsta": "isplata", "opis": "Uredski materijal"},
            {"suggested_konto": "5000"},
            "K001",
        )
        assert p.document_type == "blagajna"
        assert any(l["konto"] == "1400" for l in p.lines)  # Blagajna

    def test_from_petty_cash_over_limit(self):
        p = self.pipeline.from_petty_cash(
            {"iznos": 15000, "vrsta": "isplata", "opis": "Veliko plaćanje"},
            {"suggested_konto": "7800"},
            "K001",
        )
        assert len(p.warnings) > 0
        assert "10.000" in p.warnings[0]

    def test_from_travel_expense(self):
        p = self.pipeline.from_travel_expense({
            "km": 300, "dnevnica": 26.55, "ostali_troskovi": 80,
            "djelatnik": "Ana H.", "odrediste": "Split",
        }, "K001")
        assert p.document_type == "putni_nalog"
        assert any(l["konto"] == "5420" for l in p.lines)  # Km naknada
        assert any(l["konto"] == "5410" for l in p.lines)  # Dnevnica

    def test_from_depreciation(self):
        p = self.pipeline.from_depreciation("Laptop Dell", 125.0, "K001")
        assert p.document_type == "amortizacija"
        assert p.lines[0]["konto"] == "5300"
        assert p.lines[1]["konto"] == "0290"

    def test_from_ios(self):
        p = self.pipeline.from_ios(
            {"razlika": -150, "partner": "XYZ d.o.o.", "oib": "12345678903"},
            "K001",
        )
        assert p.document_type == "ios"
        assert p.ukupni_iznos == 150


# ═══════════════════════════════════════════════════════
# JOPPD OBRAZAC
# ═══════════════════════════════════════════════════════

class TestJOPPD:
    def setup_method(self):
        from nyx_light.modules.joppd import JOPPDGenerator
        from nyx_light.modules.payroll import PayrollEngine, Employee
        self.gen = JOPPDGenerator()
        self.pe = PayrollEngine()
        self.Employee = Employee

    def test_generate_from_payroll(self):
        employees = [
            self.Employee(name="Ana H.", bruto_placa=2000, city="Zagreb"),
            self.Employee(name="Marko K.", bruto_placa=1500, city="Split"),
        ]
        results = [self.pe.calculate(e) for e in employees]
        joppd = self.gen.from_payroll_results(
            results, oib_poslodavca="12345678903",
            naziv_poslodavca="TENA BE d.o.o.", period_month=2, period_year=2026,
        )
        assert joppd.oznaka == "2026-002"
        assert len(joppd.stavke) == 2
        assert joppd.ukupno_bruto == 3500.0
        assert joppd.ukupno_neto > 0

    def test_to_xml(self):
        emp = self.Employee(name="Test", bruto_placa=2000, city="Zagreb")
        result = self.pe.calculate(emp)
        joppd = self.gen.from_payroll_results(
            [result], "12345678903", "Test d.o.o.",
        )
        xml = self.gen.to_xml(joppd)
        assert "<?xml" in xml
        assert "<JOPPD" in xml
        assert "<BrutoIznos>2000.00</BrutoIznos>" in xml
        assert "<StranicaB>" in xml

    def test_to_dict(self):
        emp = self.Employee(name="Test", bruto_placa=1000)
        result = self.pe.calculate(emp)
        joppd = self.gen.from_payroll_results([result], "123", "Test")
        d = self.gen.to_dict(joppd)
        assert d["requires_approval"] is True
        assert d["ukupno"]["bruto"] == 1000.0


# ═══════════════════════════════════════════════════════
# OSNOVNA SREDSTVA
# ═══════════════════════════════════════════════════════

class TestOsnovnaSredstva:
    def setup_method(self):
        from nyx_light.modules.osnovna_sredstva import OsnovnaSredstvaEngine
        self.engine = OsnovnaSredstvaEngine()

    def test_add_asset(self):
        r = self.engine.add_asset({
            "naziv": "Laptop Dell", "vrsta": "računalna_oprema",
            "nabavna_vrijednost": 1200.0,
        })
        assert r["status"] == "added"
        assert r["godisnja_stopa"] == 50.0  # Računalna oprema

    def test_sitan_inventar(self):
        """Ispod 665 EUR = sitan inventar, ne dugotrajna imovina."""
        r = self.engine.add_asset({
            "naziv": "USB tipkovnica", "nabavna_vrijednost": 50.0,
        })
        assert r["status"] == "sitan_inventar"
        assert r["jednokratni_otpis"] is True
        assert r["konto"] == "1020"

    def test_monthly_depreciation(self):
        self.engine.add_asset({
            "naziv": "Server", "vrsta": "računalna_oprema",
            "nabavna_vrijednost": 6000.0,
        })
        depr = self.engine.calculate_monthly_depreciation()
        assert len(depr) == 1
        assert depr[0]["mjesecna_amortizacija"] == 250.0  # 6000 * 50% / 12

    def test_inventura_list(self):
        self.engine.add_asset({
            "naziv": "Printer", "vrsta": "uredska_oprema",
            "nabavna_vrijednost": 800.0, "lokacija": "Ured 1",
        })
        inv = self.engine.get_inventura_list()
        assert len(inv) == 1
        assert inv[0]["lokacija"] == "Ured 1"


# ═══════════════════════════════════════════════════════
# GFI PRIPREMA
# ═══════════════════════════════════════════════════════

class TestGFIPrep:
    def setup_method(self):
        from nyx_light.modules.gfi_prep import GFIPrepEngine
        self.engine = GFIPrepEngine()

    def test_kategorija_mikro(self):
        r = self.engine.kategorija_poduzetnika(
            aktiva=200_000, prihod=500_000, zaposlenici=5,
        )
        assert r["kategorija"] == "mikro"
        assert r["revizijska_obveza"] is False

    def test_kategorija_srednji(self):
        r = self.engine.kategorija_poduzetnika(
            aktiva=15_000_000, prihod=30_000_000, zaposlenici=200,
        )
        assert r["kategorija"] == "srednji"
        assert r["revizijska_obveza"] is True

    def test_bilanca_struktura(self):
        bil = self.engine.bilanca_struktura()
        assert "aktiva" in bil
        assert "pasiva" in bil
        assert "UKUPNO AKTIVA" in bil["aktiva"]["E"]["naziv"]

    def test_rdg_struktura(self):
        rdg = self.engine.rdg_struktura()
        assert "POSLOVNI PRIHODI" in rdg["stavke"]["I"]["naziv"]

    def test_zakljucna_knjizenja(self):
        cl = self.engine.zakljucna_knjizenja_checklist(2025)
        assert cl["godina"] == 2025
        assert cl["total_items"] >= 10
        assert cl["critical"] >= 4


# ═══════════════════════════════════════════════════════
# EXTERNAL PARSERS
# ═══════════════════════════════════════════════════════

class TestERacuniParser:
    def setup_method(self):
        from nyx_light.modules.eracuni_parser import ERacuniParser
        self.parser = ERacuniParser()

    def test_parse_csv(self):
        csv_data = (
            "Broj,Datum,Dobavljac,OIB,Osnovica,PDVStopa,PDVIznos,Ukupno\n"
            "R-001,2026-02-26,HEP d.d.,46830600751,800.00,25,200.00,1000.00\n"
            "R-002,2026-02-27,HT d.d.,81793146560,400.00,25,100.00,500.00\n"
        )
        results = self.parser.parse_csv(csv_data)
        assert len(results) == 2
        assert results[0]["source"] == "eRacuni"
        assert results[0]["ukupno"] == 1000.0
        assert results[0]["pdv_stopa"] == 25.0


class TestPantheonParser:
    def setup_method(self):
        from nyx_light.modules.eracuni_parser import PantheonParser
        self.parser = PantheonParser()

    def test_parse_csv(self):
        csv_data = (
            "TipDokumenta;BrojDokumenta;Datum;Konto;Partner;OIB;Opis;Duguje;Potrazuje\n"
            "UR;001;2026-02-26;7200;HEP;46830600751;Struja;1000.00;0.00\n"
            "UR;001;2026-02-26;4000;HEP;46830600751;Obveza;0.00;1000.00\n"
        )
        results = self.parser.parse_export(csv_data, fmt="csv")
        assert len(results) == 2
        assert results[0]["source"] == "Pantheon"
        assert results[0]["duguje"] == 1000.0

    def test_to_booking_proposals(self):
        records = [
            {"konto": "7200", "duguje": 500, "potrazuje": 0,
             "opis": "Usluga", "datum": "2026-02-26"},
        ]
        proposals = self.parser.to_booking_proposals(records, "K001", "CPP")
        assert len(proposals) == 1
        assert proposals[0]["erp_target"] == "CPP"
        assert proposals[0]["requires_konto_mapping"] is True


# ═══════════════════════════════════════════════════════
# E2E: KOMPLETNI TOK ULAZNI RAČUN → CPP EXPORT
# ═══════════════════════════════════════════════════════

class TestE2EInvoiceToCPP:
    """End-to-end: OCR → Kontiranje → Pipeline → Approve → CPP XML."""

    def test_full_invoice_to_cpp_flow(self):
        from nyx_light.pipeline import BookingPipeline
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        from nyx_light.export import ERPExporter

        exporter = ERPExporter(export_dir="/tmp/nyx_test_exports")
        pipeline = BookingPipeline(exporter=exporter)
        kontiranje = KontiranjeEngine()

        # 1. OCR result (simulirano)
        invoice = {
            "iznos": 1250.0, "pdv_iznos": 250.0, "pdv_stopa": 25,
            "dobavljac": "HEP d.d.", "oib": "46830600751",
            "broj_racuna": "R-2026-00567", "datum": "2026-02-26",
            "opis": "Električna energija 02/2026",
        }

        # 2. Kontiranje
        konto = kontiranje.suggest_konto("električna energija usluga")

        # 3. Pipeline submit
        proposal = pipeline.from_invoice(invoice, konto, "TENA-K001", "CPP")
        submit_result = pipeline.submit(proposal)
        assert submit_result["status"] == "pending"

        # 4. Approve
        approve_result = pipeline.approve(proposal.id, "ana.racunovoda")
        assert approve_result["status"] == "approved"

        # 5. Export to CPP
        export_result = pipeline.export_approved(
            client_id="TENA-K001", erp_target="CPP", fmt="XML"
        )
        assert export_result["status"] == "exported"
        assert export_result["erp"] == "CPP"
        assert export_result["proposals_exported"] == 1

    def test_full_payroll_to_synesis_flow(self):
        """E2E: Plaća → Pipeline → Approve → Synesis CSV."""
        from nyx_light.pipeline import BookingPipeline
        from nyx_light.modules.payroll import PayrollEngine, Employee
        from nyx_light.export import ERPExporter

        exporter = ERPExporter(export_dir="/tmp/nyx_test_exports")
        pipeline = BookingPipeline(exporter=exporter)
        pe = PayrollEngine()

        # 1. Obračun plaće
        emp = Employee(name="Ana Horvat", bruto_placa=2000, city="Zagreb", djeca=1)
        result = pe.calculate(emp)

        # 2. Pipeline submit
        proposal = pipeline.from_payroll(result, "TENA-K002", "Synesis")
        submit = pipeline.submit(proposal)
        assert submit["status"] == "pending"

        # 3. Approve
        pipeline.approve(proposal.id, "marko.racunovoda")

        # 4. Export to Synesis
        export = pipeline.export_approved(
            client_id="TENA-K002", erp_target="Synesis", fmt="CSV"
        )
        assert export["status"] == "exported"
        assert export["erp"] == "Synesis"

    def test_full_bank_statement_batch_flow(self):
        """E2E: Bankovni izvod (5 stavki) → Pipeline batch → Approve all → CPP."""
        from nyx_light.pipeline import BookingPipeline
        from nyx_light.export import ERPExporter

        exporter = ERPExporter(export_dir="/tmp/nyx_test_exports")
        pipeline = BookingPipeline(exporter=exporter)

        # 1. Bank transactions
        txs = [
            {"direction": "out", "amount": 500, "suggested_konto": "4000",
             "opis": "Plaćanje HEP", "date": "2026-02-26"},
            {"direction": "out", "amount": 300, "suggested_konto": "4000",
             "opis": "Plaćanje HT", "date": "2026-02-26"},
            {"direction": "in", "amount": 2000, "suggested_konto": "1200",
             "opis": "Naplata kupca ABC", "date": "2026-02-26"},
        ]

        # 2. Convert & submit
        proposals = pipeline.from_bank_statement(txs, "TENA-K001")
        batch = pipeline.submit_batch(proposals)
        assert batch["submitted"] == 3

        # 3. Approve all
        for pid in batch["ids"]:
            pipeline.approve(pid, "racunovoda")

        # 4. Export
        export = pipeline.export_approved(client_id="TENA-K001")
        assert export["proposals_exported"] == 3
        assert export["booking_lines"] == 6  # 2 linije per transaction
