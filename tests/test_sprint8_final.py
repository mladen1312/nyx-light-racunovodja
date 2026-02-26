"""
Sprint 8 Tests: Porez na dobit (PD), Porez na dohodak (DOH),
Bolovanje, KPI Dashboard, full E2E integration.
"""
import pytest
from datetime import date


class TestPorezNaDobit:
    """PD obrazac — godišnja prijava poreza na dobit."""

    def setup_method(self):
        from nyx_light.modules.porez_dobit import PorezDobitiEngine
        self.engine = PorezDobitiEngine()

    def test_niza_stopa_10pct(self):
        pd = self.engine.calculate(2025, ukupni_prihodi=500_000, ukupni_rashodi=400_000)
        assert pd.stopa == 10.0
        assert pd.dobit_prije_oporezivanja == 100_000
        assert pd.porez_na_dobit == 10_000  # 10% od 100k

    def test_visa_stopa_18pct(self):
        pd = self.engine.calculate(2025, ukupni_prihodi=2_000_000, ukupni_rashodi=1_500_000)
        assert pd.stopa == 18.0
        assert pd.porez_na_dobit == 90_000  # 18% od 500k

    def test_uvecanja_reprezentacija(self):
        pd = self.engine.calculate(
            2025, 800_000, 700_000,
            uvecanja={"reprezentacija_50pct": 5_000, "kazne": 2_000},
        )
        assert pd.ukupna_uvecanja == 7_000
        assert pd.porezna_osnovica == 107_000  # 100k + 7k

    def test_umanjenja(self):
        pd = self.engine.calculate(
            2025, 800_000, 700_000,
            umanjenja={"dividende": 10_000},
        )
        assert pd.porezna_osnovica == 90_000  # 100k - 10k

    def test_gubitak(self):
        pd = self.engine.calculate(2025, 400_000, 500_000)
        assert pd.dobit_prije_oporezivanja == -100_000
        assert pd.porezna_osnovica == 0
        assert pd.porez_na_dobit == 0

    def test_predujmovi_za_povrat(self):
        pd = self.engine.calculate(2025, 500_000, 400_000, placeni_predujmovi=15_000)
        assert pd.porez_na_dobit == 10_000
        assert pd.razlika_za_povrat == 5_000  # 15k - 10k

    def test_checklist_uvecanja(self):
        items = self.engine.checklist_uvecanja({"reprezentacija": 10_000})
        assert len(items) >= 7
        repr_item = [i for i in items if "Reprezentacija" in i["stavka"]][0]
        assert repr_item["iznos"] == 5_000  # 50% od 10k

    def test_to_dict(self):
        pd = self.engine.calculate(2025, 500_000, 400_000, oib="123", naziv="Test")
        d = self.engine.to_dict(pd)
        assert d["obrazac"] == "PD"
        assert d["rok_predaje"] == "30.04.2026"
        assert d["requires_approval"] is True


class TestPorezNaDohodak:
    """DOH obrazac — porez na dohodak za obrtnike."""

    def setup_method(self):
        from nyx_light.modules.porez_dohodak import PorezDohodakEngine
        self.engine = PorezDohodakEngine()

    def test_obrt_basic(self):
        doh = self.engine.calculate_obrt(
            2025, ukupni_primitci=100_000, ukupni_izdatci=60_000, grad="Zagreb",
        )
        assert doh.dohodak == 40_000
        assert doh.porezna_osnovica == 40_000 - doh.ukupni_odbitak
        assert doh.ukupno_porez_prirez > 0

    def test_obrt_s_djecom(self):
        doh_bez = self.engine.calculate_obrt(2025, 100_000, 60_000)
        doh_s = self.engine.calculate_obrt(2025, 100_000, 60_000, djeca=2)
        assert doh_s.ukupni_odbitak > doh_bez.ukupni_odbitak
        assert doh_s.ukupno_porez_prirez <= doh_bez.ukupno_porez_prirez

    def test_progresivne_stope(self):
        """Visok dohodak prolazi obje stope."""
        doh = self.engine.calculate_obrt(2025, 200_000, 50_000)
        assert doh.porez_niza_stopa > 0
        assert doh.porez_visa_stopa > 0

    def test_prirez_zagreb(self):
        doh = self.engine.calculate_obrt(2025, 100_000, 60_000, grad="Zagreb")
        assert doh.prirez_stopa == 18.0
        assert doh.prirez > 0

    def test_predujmovi(self):
        doh = self.engine.calculate_obrt(
            2025, 100_000, 60_000, placeni_predujmovi=20_000,
        )
        assert doh.razlika_za_povrat > 0 or doh.razlika_za_uplatu >= 0

    def test_pausalni_obrt(self):
        r = self.engine.calculate_pausalni(2025, godisnji_prihod=25_000)
        assert r["vrsta"] == "pausalni_obrt"
        assert r["porez"] > 0
        assert r["tromjesecni_predujam"] > 0

    def test_pausalni_obrt_preg_praga(self):
        r = self.engine.calculate_pausalni(2025, godisnji_prihod=50_000)
        assert r["error"] is True

    def test_to_dict(self):
        doh = self.engine.calculate_obrt(2025, 100_000, 60_000, oib="123")
        d = self.engine.to_dict(doh)
        assert d["obrazac"] == "DOH"
        assert d["rok_predaje"] == "28.02.2026"


class TestBolovanje:
    """Bolovanje — obračun naknade."""

    def setup_method(self):
        from nyx_light.modules.bolovanje import BolovanjeEngine
        self.engine = BolovanjeEngine()

    def test_bolest_42_dana(self):
        r = self.engine.calculate("Ana H.", "bolest", 42, 2000.0)
        assert r.dani_poslodavac == 42
        assert r.dani_hzzo == 0
        assert r.naknada_pct == 70.0
        assert r.naknada_ukupno > 0

    def test_bolest_60_dana(self):
        r = self.engine.calculate("Ana H.", "bolest", 60, 2000.0)
        assert r.dani_poslodavac == 42
        assert r.dani_hzzo == 18
        assert len(r.warnings) > 0  # HZZO doznaka

    def test_ozljeda_na_radu_100pct(self):
        r = self.engine.calculate("Marko K.", "ozljeda_na_radu", 30, 2000.0)
        assert r.naknada_pct == 100.0
        assert r.dani_poslodavac == 0
        assert r.dani_hzzo == 30

    def test_minimum_naknada(self):
        """Niska plaća → naknada se podiže na minimum."""
        r = self.engine.calculate("Test", "bolest", 10, 500.0)
        assert r.korigirana is True

    def test_booking_lines(self):
        r = self.engine.calculate("Test", "bolest", 50, 2000.0)
        lines = self.engine.booking_lines(r)
        assert len(lines) >= 2  # Poslodavac + HZZO + obveza
        kontos = [l["konto"] for l in lines]
        assert "5200" in kontos or "1250" in kontos


class TestKPIDashboard:
    """KPI financijski pokazatelji."""

    def setup_method(self):
        from nyx_light.modules.kpi import KPIDashboard, FinancialData
        self.kpi = KPIDashboard()
        self.FinancialData = FinancialData

    def _sample_data(self):
        return self.FinancialData(
            kratkotrajna_imovina=500_000, zalihe=100_000,
            novac_i_ekvivalenti=50_000, potraživanja=200_000,
            ukupna_aktiva=1_000_000, kratkorocne_obveze=250_000,
            dugorocne_obveze=200_000, ukupne_obveze=450_000,
            kapital=550_000, prihodi=2_000_000, rashodi=1_800_000,
            dobit_prije_oporezivanja=200_000, neto_dobit=160_000,
            troskovi_kamata=10_000, amortizacija=50_000,
            broj_zaposlenih=10,
        )

    def test_all_kpis(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert "likvidnost" in result
        assert "profitabilnost" in result
        assert "zaduzenost" in result
        assert "aktivnost" in result
        assert "ebitda" in result
        assert "ocjena" in result

    def test_tekuca_likvidnost(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["likvidnost"]["tekuca_likvidnost"] == 2.0  # 500k/250k

    def test_roa(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["profitabilnost"]["roa_pct"] == 16.0  # 160k/1M * 100

    def test_zaduzenost(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["zaduzenost"]["koef_zaduzenosti_pct"] == 45.0

    def test_ebitda(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["ebitda"]["ebitda"] == 260_000  # 200k + 10k + 50k

    def test_per_employee(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["po_zaposleniku"]["prihod_po_zaposleniku"] == 200_000

    def test_health_score(self):
        result = self.kpi.calculate_all(self._sample_data())
        assert result["ocjena"]["score"] >= 7.0  # Healthy company
        assert result["ocjena"]["status"] in ("Odlično", "Dobro")


class TestE2ESprint8:
    """E2E integracija Sprint 8 modula kroz NyxLightApp."""

    def setup_method(self):
        from nyx_light.app import NyxLightApp
        from nyx_light.registry import ClientConfig
        self.app = NyxLightApp(export_dir="/tmp/nyx_sprint8_test")
        self.app.register_client(ClientConfig(
            id="DOO-001", naziv="Firma d.o.o.", oib="12345678903",
            erp_target="CPP", kategorija="mali",
        ))
        self.app.register_client(ClientConfig(
            id="OBRT-001", naziv="Obrt Test", oib="98765432106",
            erp_target="Synesis", kategorija="mikro",
        ))

    def test_porez_dobit_e2e(self):
        result = self.app.prepare_porez_dobit(
            "DOO-001", 2025, 800_000, 700_000,
            uvecanja={"reprezentacija_50pct": 3_000},
        )
        assert result["obrazac"] == "PD"
        assert result["stopa"] == "10.0%"
        assert result["za_uplatu"] > 0

    def test_porez_dohodak_e2e(self):
        result = self.app.prepare_porez_dohodak(
            "OBRT-001", 2025, primitci=100_000, izdatci=60_000,
            djeca=1, grad="Zagreb",
        )
        assert result["obrazac"] == "DOH"
        assert result["dohodak"] == 40_000

    def test_bolovanje_e2e(self):
        result = self.app.process_sick_leave(
            "Ana Horvat", "bolest", 30, 2000.0, "DOO-001",
        )
        assert result["status"] == "pending"
        assert result["bolovanje"]["teret_poslodavac"] > 0
        assert result["bolovanje"]["dani_hzzo"] == 0  # 30 < 42

    def test_bolovanje_hzzo_e2e(self):
        result = self.app.process_sick_leave(
            "Marko K.", "ozljeda_na_radu", 20, 2500.0, "DOO-001",
        )
        assert result["bolovanje"]["teret_hzzo"] > 0
        assert result["bolovanje"]["dani_poslodavac"] == 0

    def test_kpi_e2e(self):
        from nyx_light.modules.kpi import FinancialData
        data = FinancialData(
            kratkotrajna_imovina=300_000, zalihe=50_000,
            novac_i_ekvivalenti=30_000, potraživanja=100_000,
            ukupna_aktiva=600_000, kratkorocne_obveze=150_000,
            dugorocne_obveze=100_000, ukupne_obveze=250_000,
            kapital=350_000, prihodi=1_000_000, rashodi=900_000,
            dobit_prije_oporezivanja=100_000, neto_dobit=82_000,
            amortizacija=20_000, broj_zaposlenih=5,
        )
        result = self.app.calculate_kpi(data)
        assert result["likvidnost"]["tekuca_likvidnost"] == 2.0
        assert result["ocjena"]["score"] >= 5.0

    def test_system_status_includes_new_modules(self):
        status = self.app.get_system_status()
        assert "porez_dobit" in status["modules"]
        assert "porez_dohodak" in status["modules"]
        assert "bolovanje" in status["modules"]
        assert "kpi" in status["modules"]
