"""
Sprint 9 (FINAL): Kadrovska, Intrastat, GFI XML, Fakturiranje, Likvidacija, Web UI.
"""
import pytest


class TestKadrovska:
    """B5: Kadrovska evidencija."""

    def setup_method(self):
        from nyx_light.modules.kadrovska import KadrovskaEvidencija, Zaposlenik
        self.ke = KadrovskaEvidencija()
        self.Zaposlenik = Zaposlenik

    def _sample(self, **kw):
        defaults = dict(id="Z001", ime="Ana", prezime="Horvat", oib="12345678901",
                        bruto_placa=1500.0, datum_zaposlenja="2024-01-15")
        defaults.update(kw)
        return self.Zaposlenik(**defaults)

    def test_add_employee(self):
        r = self.ke.add(self._sample())
        assert r["success"] is True

    def test_invalid_oib(self):
        r = self.ke.add(self._sample(oib="123"))
        assert r["success"] is False

    def test_below_min_wage(self):
        r = self.ke.add(self._sample(bruto_placa=500.0))
        assert r["success"] is False

    def test_list_active(self):
        self.ke.add(self._sample(id="Z001"))
        self.ke.add(self._sample(id="Z002", oib="98765432109"))
        assert len(self.ke.list_active()) == 2

    def test_deactivate(self):
        self.ke.add(self._sample())
        self.ke.deactivate("Z001", "2026-01-31", "sporazumni")
        assert len(self.ke.list_active()) == 0

    def test_godisnji_odmor(self):
        self.ke.add(self._sample())
        r = self.ke.record_godisnji("Z001", 5)
        assert r["success"] is True
        assert r["preostalo"] == 15  # 20 - 5

    def test_godisnji_prekoracenje(self):
        self.ke.add(self._sample())
        r = self.ke.record_godisnji("Z001", 25)  # > 20
        assert len(r["warnings"]) > 0

    def test_payroll_data(self):
        self.ke.add(self._sample(broj_djece=2))
        pd = self.ke.payroll_data("Z001")
        assert pd["bruto"] == 1500.0
        assert pd["broj_djece"] == 2

    def test_staz_report(self):
        self.ke.add(self._sample())
        report = self.ke.staz_report()
        assert len(report) == 1
        assert report[0]["staz_godina"] >= 0


class TestIntrastat:
    """C6: Intrastat prijava."""

    def setup_method(self):
        from nyx_light.modules.intrastat import IntrastatEngine, IntrastatStavka
        self.engine = IntrastatEngine()
        self.Stavka = IntrastatStavka

    def test_check_obligation_below(self):
        r = self.engine.check_obligation(primitak_ytd=100_000)
        assert r["primitak"]["obveznik"] is False

    def test_check_obligation_above(self):
        r = self.engine.check_obligation(primitak_ytd=500_000)
        assert r["primitak"]["obveznik"] is True

    def test_create_prijava(self):
        stavke = [
            self.Stavka(tarifni_broj="85171200", opis_robe="Mobilni telefoni",
                        zemlja_partner="DE", masa_kg=100, fakturna_vrijednost_eur=50_000,
                        zemlja_podrijetla="CN"),
            self.Stavka(tarifni_broj="84713000", opis_robe="Laptopi",
                        zemlja_partner="IT", masa_kg=200, fakturna_vrijednost_eur=80_000,
                        zemlja_podrijetla="TW"),
        ]
        p = self.engine.create_prijava(2025, 6, "primitak", stavke, oib="123")
        assert p.broj_stavki == 2
        assert p.ukupna_vrijednost == 130_000

    def test_aggregate_by_country(self):
        stavke = [
            self.Stavka(tarifni_broj="12345678", zemlja_partner="DE",
                        fakturna_vrijednost_eur=50_000, masa_kg=100, zemlja_podrijetla="DE"),
            self.Stavka(tarifni_broj="12345679", zemlja_partner="DE",
                        fakturna_vrijednost_eur=30_000, masa_kg=50, zemlja_podrijetla="DE"),
            self.Stavka(tarifni_broj="12345680", zemlja_partner="IT",
                        fakturna_vrijednost_eur=20_000, masa_kg=80, zemlja_podrijetla="IT"),
        ]
        p = self.engine.create_prijava(2025, 6, "primitak", stavke)
        agg = self.engine.aggregate_by_country(p)
        assert len(agg) == 2
        de = [a for a in agg if a["zemlja"] == "DE"][0]
        assert de["vrijednost"] == 80_000
        assert de["broj_stavki"] == 2

    def test_validation_hr_partner(self):
        stavke = [
            self.Stavka(tarifni_broj="12345678", zemlja_partner="HR",
                        fakturna_vrijednost_eur=1000, masa_kg=10, zemlja_podrijetla="HR"),
        ]
        p = self.engine.create_prijava(2025, 6, "primitak", stavke)
        assert any("HR" in w for w in p.warnings)

    def test_to_dict(self):
        stavke = [self.Stavka(tarifni_broj="12345678", zemlja_partner="DE",
                              fakturna_vrijednost_eur=50_000, masa_kg=100, zemlja_podrijetla="DE")]
        p = self.engine.create_prijava(2025, 6, "primitak", stavke)
        d = self.engine.to_dict(p)
        assert d["obrazac"] == "Intrastat"
        assert d["requires_approval"] is True


class TestGFIXML:
    """D6: GFI XML za FINA."""

    def setup_method(self):
        from nyx_light.modules.gfi_xml import GFIXMLGenerator
        self.gen = GFIXMLGenerator()

    def test_generate_basic(self):
        result = self.gen.generate(
            oib="12345678903", naziv="Test d.o.o.", godina=2025,
            kategorija="mikro",
            bilanca={"040": 100_000, "065": 100_000},
            rdg={"140": 200_000, "150": 180_000, "170": 20_000},
        )
        assert "xml" in result
        assert "GFI" in result["xml"]
        assert result["filename"] == "GFI_12345678903_2025.xml"
        assert result["rok"] == "30.04.2026"

    def test_srednji_has_more_obrazci(self):
        r = self.gen.generate("123", "T", 2025, "srednji", {}, {})
        assert "NTI" in r["obrazci"]
        assert "PK" in r["obrazci"]

    def test_validate_balance_ok(self):
        r = self.gen.validate_balance({"040": 500_000, "065": 500_000})
        assert r["valid"] is True

    def test_validate_balance_mismatch(self):
        r = self.gen.validate_balance({"040": 500_000, "065": 499_000})
        assert r["valid"] is False
        assert r["razlika"] == 1000

    def test_xml_contains_aop(self):
        result = self.gen.generate("123", "T", 2025, "mali",
                                    {"040": 100_000}, {"170": 20_000})
        assert 'aop="040"' in result["xml"]
        assert 'aop="170"' in result["xml"]


class TestFakturiranje:
    """F3: Fakturiranje usluga ureda."""

    def setup_method(self):
        from nyx_light.modules.fakturiranje import FakturiranjeEngine
        self.engine = FakturiranjeEngine(
            ured_naziv="Ured Test", ured_oib="99988877766",
            ured_iban="HR1234567890123456789",
        )

    def test_monthly_invoice_mikro(self):
        r = self.engine.create_monthly_invoice("K001", "Firma", "123", "mikro")
        assert r.ukupno_bez_pdv == 150.0  # paušal mikro
        assert r.ukupno_pdv == 37.5  # 25%
        assert r.ukupno_s_pdv == 187.5

    def test_monthly_invoice_s_placama(self):
        r = self.engine.create_monthly_invoice("K001", "Firma", "123", "mali",
                                                broj_zaposlenih=5)
        assert len(r.stavke) == 3  # paušal + plaće + JOPPD
        assert r.ukupno_bez_pdv > 300  # 300 paušal + 75 plaće + 20 JOPPD

    def test_extra_items(self):
        r = self.engine.create_monthly_invoice("K001", "F", "1", "mikro",
                                                extra_items=[{"opis": "PD obrazac", "cijena": 100}])
        assert len(r.stavke) == 2
        assert r.ukupno_bez_pdv == 250.0  # 150 + 100

    def test_to_dict(self):
        r = self.engine.create_monthly_invoice("K001", "Firma", "123", "mikro")
        d = self.engine.to_dict(r)
        assert "broj" in d
        assert d["ukupno_s_pdv"] == 187.5

    def test_unpaid_tracking(self):
        self.engine.create_monthly_invoice("K001", "Firma A", "1", "mikro")
        self.engine.create_monthly_invoice("K002", "Firma B", "2", "mali")
        unpaid = self.engine.get_unpaid()
        assert len(unpaid) == 2

    def test_mark_paid(self):
        r = self.engine.create_monthly_invoice("K001", "Firma", "1", "mikro")
        self.engine.mark_paid(r.broj)
        assert len(self.engine.get_unpaid()) == 0


class TestLikvidacija:
    """G3: Likvidacijsko računovodstvo."""

    def setup_method(self):
        from nyx_light.modules.likvidacija import LikvidacijaEngine
        self.engine = LikvidacijaEngine()

    def test_start_liquidation(self):
        s = self.engine.start("K001", "Firma d.o.o.", "123", "2026-01-15", "Ivan I.")
        assert s.faza == "priprema"
        assert len(s.checklist) == 20

    def test_advance_phase(self):
        self.engine.start("K001", "F", "1", "2026-01-15", "L")
        r = self.engine.advance_phase("K001", "registracija")
        assert r["success"] is True
        s = self.engine.get_status("K001")
        assert s.faza == "registracija"

    def test_checklist_has_all_phases(self):
        s = self.engine.start("K001", "F", "1", "2026-01-15", "L")
        faze = set(c["faza"] for c in s.checklist)
        assert faze == {"priprema", "registracija", "vjerovnici", "izvjestaji", "zavrsna"}

    def test_knjizenja_likvidacija(self):
        knjizenja = self.engine.knjizenja_likvidacija()
        assert len(knjizenja) >= 5

    def test_to_dict(self):
        s = self.engine.start("K001", "Firma", "123", "2026-01-15", "Ivan")
        d = self.engine.to_dict(s)
        assert d["progress"] == "0/20"
        assert d["progress_pct"] == 0.0
        assert "tipicna_knjizenja" in d


class TestWebUI:
    """Web UI — basic structure test."""

    def test_import(self):
        from nyx_light.ui.web import create_app, _FRONTEND_HTML, HAS_FASTAPI
        assert _FRONTEND_HTML is not None
        assert "Nyx Light" in _FRONTEND_HTML

    def test_frontend_html_complete(self):
        from nyx_light.ui.web import _FRONTEND_HTML
        assert "chatBox" in _FRONTEND_HTML
        assert "pendingList" in _FRONTEND_HTML
        assert "deadlineList" in _FRONTEND_HTML
        assert "/api/chat" in _FRONTEND_HTML
        assert "/api/pending" in _FRONTEND_HTML
        assert "WebSocket" in _FRONTEND_HTML


class TestE2ESprint9:
    """E2E integracija svih finalnih modula."""

    def setup_method(self):
        from nyx_light.app import NyxLightApp
        from nyx_light.registry import ClientConfig
        self.app = NyxLightApp(export_dir="/tmp/nyx_sprint9_test")
        self.app.register_client(ClientConfig(
            id="DOO-001", naziv="Firma d.o.o.", oib="12345678903",
            erp_target="CPP", kategorija="mali",
        ))

    def test_kadrovska_e2e(self):
        from nyx_light.modules.kadrovska import Zaposlenik
        z = Zaposlenik(id="Z001", ime="Ana", prezime="H.", oib="12345678901",
                       bruto_placa=1500, datum_zaposlenja="2024-01-15")
        r = self.app.kadrovska.add(z)
        assert r["success"] is True
        pd = self.app.kadrovska.payroll_data("Z001")
        assert pd["bruto"] == 1500

    def test_intrastat_e2e(self):
        r = self.app.check_intrastat_obligation(primitak_ytd=500_000)
        assert r["primitak"]["obveznik"] is True

    def test_gfi_xml_e2e(self):
        r = self.app.generate_gfi_xml(
            "DOO-001", 2025,
            bilanca={"040": 500_000, "065": 500_000},
            rdg={"140": 1_000_000, "150": 900_000, "170": 80_000},
        )
        assert "xml" in r
        assert "12345678903" in r["xml"]

    def test_fakturiranje_e2e(self):
        r = self.app.create_service_invoice("DOO-001", broj_zaposlenih=3)
        assert r["ukupno_s_pdv"] > 0

    def test_likvidacija_e2e(self):
        r = self.app.start_liquidation("DOO-001", "2026-02-01", "Dr. Mešter")
        assert r["progress"] == "0/20"
        assert r["faza"] == "priprema"

    def test_system_status_complete(self):
        status = self.app.get_system_status()
        for mod in ["kadrovska", "intrastat", "gfi_xml", "fakturiranje", "likvidacija"]:
            assert mod in status["modules"], f"Missing: {mod}"
