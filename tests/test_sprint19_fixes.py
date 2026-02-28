"""
Sprint 19 — Tests za sve popravke:
- Kontiranje engine (65+ rules)
- Bank parser (Erste/Zaba/PBZ)
- Blagajna (nalozi, izvještaj, limiti)
- Putni nalozi (dnevnice, PN obrazac)
- Porez na dobit (PD obrazac)
- GFI XML (Bilanca, RDG)
- LLM Request Queue (semaphore, rate limit)
"""

import asyncio
import pytest
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ═══════════════════════════════════════════
# KONTIRANJE ENGINE
# ═══════════════════════════════════════════

class TestKontiranjeEngine:
    def setup_method(self):
        from nyx_light.modules.kontiranje.engine import KontiranjeEngine
        self.engine = KontiranjeEngine()

    def test_rule_ulazni_materijal(self):
        p = self.engine.suggest_konto("Nabava materijala za proizvodnju", tip_dokumenta="ulazni")
        assert p.duguje_konto in ("4009", "4091"), f"Got {p.duguje_konto}"
        assert p.potrazuje_konto == "2200"
        assert p.confidence >= 0.7
        assert p.source == "rule_engine"

    def test_rule_struja_hep(self):
        p = self.engine.suggest_konto("Račun za struju HEP", tip_dokumenta="ulazni")
        assert p.duguje_konto == "4030"
        assert p.confidence >= 0.85

    def test_rule_gorivo(self):
        p = self.engine.suggest_konto("Gorivo dizel", tip_dokumenta="ulazni")
        assert p.duguje_konto == "4070"
        assert p.confidence >= 0.85

    def test_rule_reprezentacija_warning(self):
        p = self.engine.suggest_konto("Reprezentacija restoran ručak", tip_dokumenta="ulazni")
        assert p.duguje_konto == "4094"
        assert "nepriznato" in p.napomena.lower() or "30%" in p.napomena

    def test_rule_banka_uplata(self):
        p = self.engine.suggest_konto("Uplata kupca po računu", tip_dokumenta="banka_uplata")
        assert p.duguje_konto == "1500"
        assert p.potrazuje_konto == "1200"

    def test_rule_banka_placa(self):
        p = self.engine.suggest_konto("Isplata neto plaća JOPPD", tip_dokumenta="banka_isplata")
        assert p.duguje_konto == "4500"
        assert p.potrazuje_konto == "1500"

    def test_rule_amortizacija(self):
        p = self.engine.suggest_konto("Amortizacija opreme", tip_dokumenta="amortizacija")
        assert p.duguje_konto == "4302"
        assert p.confidence >= 0.90

    def test_rule_izlazni_usluga(self):
        p = self.engine.suggest_konto("Usluga konzaltinga", tip_dokumenta="izlazni")
        assert p.duguje_konto == "1200"
        assert "7510" in p.potrazuje_konto or "7500" in p.potrazuje_konto

    def test_supplier_pattern_a1(self):
        p = self.engine.suggest_konto("Račun", supplier_name="A1 Hrvatska d.o.o.")
        assert p.duguje_konto == "4040"
        assert p.source in ("supplier_pattern", "rule_engine")  # A1 in regex too

    def test_supplier_pattern_ina(self):
        p = self.engine.suggest_konto("Gorivo", supplier_name="INA d.d.")
        assert p.duguje_konto == "4070"

    def test_memory_hint(self):
        p = self.engine.suggest_konto(
            "Račun", memory_hint={"hint": "4041", "duguje": "4041", "confidence": 0.92, "count": 15}
        )
        assert p.duguje_konto == "4041"
        assert p.source == "L2_semantic_memory"
        assert p.confidence >= 0.90

    def test_fallback(self):
        p = self.engine.suggest_konto("xyz nepoznati opis", tip_dokumenta="ulazni")
        assert p.confidence <= 0.40
        assert p.source == "keyword_fallback"

    def test_pdv_konto_13pct(self):
        p = self.engine.suggest_konto("Usluga", tip_dokumenta="ulazni", pdv_stopa=13.0)
        assert p.pdv_konto == "1231"

    def test_suggest_batch(self):
        stavke = [
            {"opis": "Struja HEP", "tip": "ulazni", "iznos": 500},
            {"opis": "Uplata kupca", "tip": "banka_uplata", "iznos": 1000},
        ]
        results = self.engine.suggest_batch(stavke)
        assert len(results) == 2
        assert results[0].duguje_konto == "4030"
        assert results[1].duguje_konto == "1500"

    def test_stats(self):
        self.engine.suggest_konto("Struja", tip_dokumenta="ulazni")
        stats = self.engine.get_stats()
        assert stats["total"] >= 1
        assert stats["rules_count"] > 50
        assert stats["kontni_plan_count"] > 100

    def test_keyword_search(self):
        from nyx_light.modules.kontiranje.engine import suggest_konto_by_keyword
        results = suggest_konto_by_keyword("oprema")
        assert len(results) > 0
        assert any("oprema" in r["naziv"].lower() for r in results)

    def test_all_rules_compile(self):
        from nyx_light.modules.kontiranje.engine import _COMPILED_RULES
        assert len(_COMPILED_RULES) >= 50


# ═══════════════════════════════════════════
# BANK PARSER
# ═══════════════════════════════════════════

class TestBankParser:
    def setup_method(self):
        from nyx_light.modules.bank_parser.parser import BankStatementParser
        self.parser = BankStatementParser()

    def test_detect_bank_erste(self):
        assert self.parser.detect_bank("HR0210000012345678901") == "Erste"

    def test_detect_bank_zaba(self):
        assert self.parser.detect_bank("HR2323600001234567890") == "Zaba"

    def test_detect_bank_pbz(self):
        assert self.parser.detect_bank("HR1723400001234567890") == "PBZ"

    def test_detect_bank_otp(self):
        assert self.parser.detect_bank("HR3623860021234567890") == "OTP"

    def test_parse_erste_csv(self):
        """Test Erste CSV format parsing."""
        csv_content = "Datum knjiženja;Datum valute;Opis;Iznos;Valuta;Saldo\n"
        csv_content += "15.01.2026;15.01.2026;Uplata kupca IVIĆ;1.500,00;EUR;25.000,00\n"
        csv_content += "16.01.2026;16.01.2026;Plaćanje dobavljaču;-2.300,50;EUR;22.699,50\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            path = f.name

        try:
            results = self.parser.parse(path, bank="erste")
            assert len(results) == 2
            assert results[0]["iznos"] == 1500.0
            assert results[0]["tip"] == "uplata"
            assert results[1]["iznos"] == -2300.5
            assert results[1]["tip"] == "isplata"
            assert results[0]["banka"] == "Erste"
        finally:
            os.unlink(path)

    def test_parse_zaba_csv(self):
        """Test Zaba CSV format (terećenje/odobrenje u odvojenim stupcima)."""
        csv_content = "Datum;Opis transakcije;Terećenje;Odobrenje;Saldo\n"
        csv_content += "15.01.2026;Uplata;;5.000,00;30.000,00\n"
        csv_content += "16.01.2026;Plaćanje najma;3.000,00;;27.000,00\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            path = f.name

        try:
            results = self.parser.parse(path, bank="zaba")
            assert len(results) == 2
            assert results[0]["tip"] == "uplata"
            assert results[0]["iznos"] == 5000.0
            assert results[1]["tip"] == "isplata"
            assert results[1]["banka"] == "Zaba"
        finally:
            os.unlink(path)

    def test_parse_pbz_csv(self):
        """Test PBZ CSV format."""
        csv_content = "Datum;Vrsta;Opis;Iznos;Valuta;Stanje;Naziv;IBAN;Poziv na broj\n"
        csv_content += "15.01.2026;Uplata;Naplata;2000.00;EUR;28000.00;Kupac d.o.o.;HR1723400099887766554;HR00-123\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            path = f.name

        try:
            results = self.parser.parse(path, bank="pbz")
            assert len(results) == 1
            assert results[0]["iznos"] == 2000.0
            assert results[0]["banka"] == "PBZ"
        finally:
            os.unlink(path)

    def test_auto_detect_zaba(self):
        csv_content = "Datum;Opis transakcije;Terećenje;Odobrenje;Saldo\n"
        csv_content += "15.01.2026;Test;;100,00;100,00\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_content)
            path = f.name
        try:
            detected = self.parser._detect_bank_from_csv(Path(path))
            assert detected == "zaba"
        finally:
            os.unlink(path)

    def test_parse_amount_hr_format(self):
        assert self.parser._parse_amount("1.500,00") == 1500.0
        assert self.parser._parse_amount("2.300,50") == 2300.5
        assert self.parser._parse_amount("-500,00") == -500.0

    def test_parse_amount_us_format(self):
        assert self.parser._parse_amount("1500.00") == 1500.0
        assert self.parser._parse_amount("-2300.50") == -2300.5

    def test_unsupported_format(self):
        with tempfile.NamedTemporaryFile(suffix='.xyz', delete=False) as f:
            path = f.name
        try:
            with pytest.raises(ValueError):
                self.parser.parse(path)
        finally:
            os.unlink(path)

    def test_stats(self):
        stats = self.parser.get_stats()
        assert "Erste" in stats["supported_banks"]
        assert "Zaba" in stats["supported_banks"]
        assert "PBZ" in stats["supported_banks"]


# ═══════════════════════════════════════════
# BLAGAJNA
# ═══════════════════════════════════════════

class TestBlagajna:
    def setup_method(self):
        from nyx_light.modules.blagajna.validator import BlagajnaValidator
        self.bv = BlagajnaValidator()

    def test_uplatnica(self):
        nalog = self.bv.kreiraj_nalog(tip="uplatnica", iznos=500, opis="Gotovinska uplata kupca")
        assert nalog.redni_broj == 1
        assert nalog.tip == "uplatnica"
        assert nalog.konto_duguje == "1400"
        assert self.bv.get_saldo() == 500

    def test_isplatnica(self):
        self.bv.kreiraj_nalog(tip="uplatnica", iznos=1000, opis="Uplata")
        nalog = self.bv.kreiraj_nalog(tip="isplatnica", iznos=300, opis="Nabava materijala",
                                       kategorija="materijal")
        assert nalog.konto_duguje == "4009"
        assert nalog.konto_potrazuje == "1400"
        assert self.bv.get_saldo() == 700

    def test_limit_gotovine_error(self):
        nalog = self.bv.kreiraj_nalog(tip="uplatnica", iznos=15000, opis="Velika uplata")
        assert len(nalog.validacijske_greske) > 0
        assert any("10.000" in e or "limit" in e.lower() for e in nalog.validacijske_greske)

    def test_negativni_saldo_error(self):
        nalog = self.bv.kreiraj_nalog(tip="isplatnica", iznos=5000, opis="Isplata bez sredstava")
        assert any("minus" in e.lower() or "nedovoljno" in e.lower()
                    for e in nalog.validacijske_greske)

    def test_reprezentacija_warning(self):
        self.bv.kreiraj_nalog(tip="uplatnica", iznos=5000, opis="Uplata")
        nalog = self.bv.kreiraj_nalog(
            tip="isplatnica", iznos=200, opis="Ručak", kategorija="reprezentacija"
        )
        assert any("30%" in w or "nepriznato" in w.lower() for w in nalog.upozorenja)

    def test_dnevni_izvjestaj(self):
        self.bv.kreiraj_nalog(tip="uplatnica", iznos=1000, opis="Uplata 1")
        self.bv.kreiraj_nalog(tip="uplatnica", iznos=500, opis="Uplata 2")
        self.bv.kreiraj_nalog(tip="isplatnica", iznos=300, opis="Isplata 1")

        izvjestaj = self.bv.generiraj_dnevni_izvjestaj(prethodni_saldo=2000)
        d = self.bv.izvjestaj_to_dict(izvjestaj)

        assert d["ukupno_uplate"] == 1500
        assert d["ukupno_isplate"] == 300
        assert d["novi_saldo"] == 3200
        assert d["broj_naloga"] == 3

    def test_partner_yearly_limit(self):
        oib = "12345678901"
        for i in range(11):
            self.bv.kreiraj_nalog(tip="uplatnica", iznos=500, opis="Uplata", partner_oib="")
        nalog = self.bv.kreiraj_nalog(tip="isplatnica", iznos=5001,
                                       opis="Isplata", partner_oib=oib)
        nalog2 = self.bv.kreiraj_nalog(tip="isplatnica", iznos=5001,
                                        opis="Isplata 2", partner_oib=oib)
        assert any("godišnji" in e.lower() or "limit" in e.lower()
                    for e in nalog2.validacijske_greske)

    def test_validate_transaction(self):
        result = self.bv.validate_transaction(iznos=500)
        assert result["valid"] is True

        result = self.bv.validate_transaction(iznos=15000)
        assert result["valid"] is False

    def test_numeracija(self):
        n1 = self.bv.kreiraj_nalog(tip="uplatnica", iznos=100, opis="A")
        n2 = self.bv.kreiraj_nalog(tip="uplatnica", iznos=200, opis="B")
        n3 = self.bv.kreiraj_nalog(tip="isplatnica", iznos=50, opis="C")
        assert n1.redni_broj == 1
        assert n2.redni_broj == 2
        assert n3.redni_broj == 3

    def test_stats(self):
        self.bv.kreiraj_nalog(tip="uplatnica", iznos=1000, opis="Test")
        stats = self.bv.get_stats()
        assert stats["saldo"] == 1000
        assert stats["naloga_danas"] == 1
        assert stats["limit_gotovine"] == 10000


# ═══════════════════════════════════════════
# PUTNI NALOZI
# ═══════════════════════════════════════════

class TestPutniNalozi:
    def setup_method(self):
        from nyx_light.modules.putni_nalozi.checker import PutniNaloziChecker
        self.pnc = PutniNaloziChecker()

    def test_basic_putni_nalog(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Ivan Horvat",
            odrediste="Split",
            svrha="Sastanak s klijentom",
            datum_polaska="2026-03-01",
            vrijeme_polaska="07:00",
            datum_povratka="2026-03-01",
            vrijeme_povratka="20:00",
            km_ukupno=800,
        )
        assert pn.valid
        assert pn.km_naknada_ukupno == 320.0  # 800 * 0.40
        assert pn.broj_punih_dnevnica == 1     # 13h (>12h) = puna dnevnica
        assert pn.dnevnice_ukupno == 53.08

    def test_overnight_trip(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Ana Kovač",
            odrediste="Dubrovnik",
            svrha="Konferencija",
            datum_polaska="2026-03-10",
            vrijeme_polaska="06:00",
            datum_povratka="2026-03-12",
            vrijeme_povratka="22:00",
            km_ukupno=1200,
            nocenja=2,
        )
        assert pn.valid
        assert pn.km_naknada_ukupno == 480.0
        assert pn.dnevnice_ukupno > 0

    def test_international_trip(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Marko Babić",
            odrediste="München",
            svrha="Sajam",
            datum_polaska="2026-04-01",
            vrijeme_polaska="06:00",
            datum_povratka="2026-04-03",
            vrijeme_povratka="22:00",
            km_ukupno=0,
            prijevozno_sredstvo="avion",
            zemlja="njemacka",
            nocenja=2,
        )
        assert pn.valid
        assert pn.dnevnice_ukupno > 0
        assert pn.km_naknada_ukupno == 0  # Avion, nema km

    def test_validation_errors(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="",
            odrediste="",
            svrha="",
            datum_polaska="",
            vrijeme_polaska="08:00",
            datum_povratka="",
            vrijeme_povratka="17:00",
        )
        assert not pn.valid
        assert len(pn.greske) >= 3

    def test_km_warning(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Ivan",
            odrediste="Test",
            svrha="Test",
            datum_polaska="2026-03-01",
            vrijeme_polaska="08:00",
            datum_povratka="2026-03-01",
            vrijeme_povratka="20:00",
            km_ukupno=2500,
        )
        assert any("2000" in w for w in pn.upozorenja)

    def test_dnevnice_rh(self):
        info = self.pnc.get_dnevnica_info("rh")
        assert info["puna"] == 53.08
        assert info["pola"] == 26.54

    def test_dnevnice_njemacka(self):
        info = self.pnc.get_dnevnica_info("njemacka")
        assert info["puna"] == 70.0

    def test_list_zemlje(self):
        zemlje = self.pnc.list_zemlje()
        assert len(zemlje) > 40
        assert zemlje[0]["zemlja"] == "rh"

    def test_troskovi(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Test", odrediste="Test", svrha="Test",
            datum_polaska="2026-03-01", vrijeme_polaska="06:00",
            datum_povratka="2026-03-02", vrijeme_povratka="20:00",
            troskovi=[
                {"vrsta": "cestarina", "opis": "HAC", "iznos": 50},
                {"vrsta": "parking", "opis": "Parking centar", "iznos": 20},
            ],
        )
        assert pn.troskovi_ukupno == 70.0

    def test_to_dict(self):
        pn = self.pnc.kreiraj_putni_nalog(
            zaposlenik="Test", odrediste="Split", svrha="Posao",
            datum_polaska="2026-03-01", vrijeme_polaska="08:00",
            datum_povratka="2026-03-01", vrijeme_povratka="20:00",
            km_ukupno=500,
        )
        d = self.pnc.to_dict(pn)
        assert "broj" in d
        assert "km_naknada_ukupno" in d
        assert d["km_naknada_eur_km"] == 0.40


# ═══════════════════════════════════════════
# POREZ NA DOBIT
# ═══════════════════════════════════════════

class TestPorezNaDobit:
    def setup_method(self):
        from nyx_light.modules.porez_dobit import PorezNaDobitEngine
        self.engine = PorezNaDobitEngine()

    def test_mala_stopa(self):
        pd = self.engine.calculate(prihodi=500000, rashodi=400000)
        assert pd.porezna_stopa == 0.10
        assert pd.dobit_rdg == 100000
        assert pd.porez_na_dobit == 10000

    def test_velika_stopa(self):
        pd = self.engine.calculate(prihodi=2000000, rashodi=1500000)
        assert pd.porezna_stopa == 0.18
        assert pd.dobit_rdg == 500000
        assert pd.porez_na_dobit == 90000

    def test_povecanja(self):
        pd = self.engine.calculate(
            prihodi=500000, rashodi=450000,
            reprezentacija=10000,  # 30% = 3000 nepriznato
            kazne=5000,
        )
        assert pd.reprezentacija_30pct == 3000
        assert pd.kazne_penali == 5000
        assert pd.ukupna_povecanja == 8000
        assert pd.porezna_osnovica == 58000  # 50000 + 8000

    def test_gubitak(self):
        pd = self.engine.calculate(prihodi=200000, rashodi=300000)
        assert pd.gubitak_rdg == 100000
        assert pd.porezna_osnovica == 0
        assert pd.porez_na_dobit == 0

    def test_preneseni_gubitak(self):
        pd = self.engine.calculate(prihodi=500000, rashodi=400000, preneseni_gubitak=50000)
        assert pd.preneseni_gubitak == 50000
        assert pd.osnovica_nakon_gubitka == 50000  # 100000 - 50000
        assert pd.porez_na_dobit == 5000  # 50000 * 10%

    def test_predujmovi(self):
        pd = self.engine.calculate(prihodi=500000, rashodi=400000, placeni_predujmovi=12000)
        assert pd.razlika_za_povrat == 2000  # Platio 12000, duguje 10000

    def test_to_dict(self):
        pd = self.engine.calculate(prihodi=800000, rashodi=600000, reprezentacija=5000)
        d = self.engine.to_dict(pd)
        assert "prihodi" in d
        assert "stopa" in d
        assert "za_uplatu" in d
        assert d["stopa"] == "10%"


# ═══════════════════════════════════════════
# GFI XML
# ═══════════════════════════════════════════

class TestGFIXML:
    def setup_method(self):
        from nyx_light.modules.gfi_xml import GFIXMLGenerator
        self.gen = GFIXMLGenerator()

    def test_bilanca_basic(self):
        data = {
            "041": 50000.0,   # Novac u banci
            "036": 100000.0,  # Potraživanja od kupaca
            "012": 200000.0,  # Oprema
            "045": 100000.0,  # Temeljni kapital
            "061": 80000.0,   # Dobavljači
        }
        izvj = self.gen.generate_bilanca(data, oib="12345678901", naziv="Test d.o.o.")
        d = self.gen.to_dict(izvj)
        assert d["izvjestaj"] == "Bilanca"
        assert d["oib"] == "12345678901"
        assert d["ukupno_aop_pozicija"] > 0

    def test_bilanca_auto_sum(self):
        data = {
            "010": 100000.0,  # Zemljišta
            "012": 200000.0,  # Oprema
            "041": 50000.0,   # Novac
        }
        izvj = self.gen.generate_bilanca(data)
        poz = {p.aop: p.tekuce for p in izvj.pozicije}
        # Materijalna (009) should be auto-summed
        assert poz.get("009", 0) == 300000.0  # 100000 + 200000

    def test_rdg(self):
        data = {
            "102": 1000000.0,  # Prihodi od prodaje
            "106": 400000.0,   # Materijalni troškovi
            "109": 300000.0,   # Troškovi osoblja
            "112": 50000.0,    # Amortizacija
        }
        izvj = self.gen.generate_rdg(data, oib="12345678901", naziv="Test d.o.o.")
        d = self.gen.to_dict(izvj)
        assert d["izvjestaj"] == "Račun dobiti i gubitka"
        assert d["ukupno_aop_pozicija"] > 0

    def test_xml_generation(self):
        data = {"041": 50000.0, "045": 50000.0}
        izvj = self.gen.generate_bilanca(data, oib="12345678901")
        xml = self.gen.to_xml(izvj)
        assert "<?xml" in xml
        assert "<GFI" in xml
        assert "<OIB>12345678901</OIB>" in xml
        assert "<AOP>041</AOP>" in xml

    def test_available_reports(self):
        reports = self.gen.get_available_reports()
        assert "Bilanca" in reports
        assert "RDG" in reports


# ═══════════════════════════════════════════
# LLM REQUEST QUEUE
# ═══════════════════════════════════════════

class TestLLMRequestQueue:
    def test_basic_submit(self):
        from nyx_light.llm.request_queue import LLMRequestQueue

        async def fake_llm(*args, **kwargs):
            return {"content": "test response"}

        async def run():
            queue = LLMRequestQueue(max_concurrent=3, max_per_minute=10)
            result = await queue.submit("user1", fake_llm, "hello")
            assert result["content"] == "test response"

        asyncio.run(run())

    def test_rate_limiting(self):
        from nyx_light.llm.request_queue import LLMRequestQueue, RateLimitError

        async def fake_llm(*args, **kwargs):
            return {"content": "ok"}

        async def run():
            queue = LLMRequestQueue(max_concurrent=3, max_per_minute=3)
            # Send 3 requests — should work
            for i in range(3):
                await queue.submit("user1", fake_llm)
            # 4th should fail
            with pytest.raises(RateLimitError):
                await queue.submit("user1", fake_llm)

        asyncio.run(run())

    def test_different_users_independent(self):
        from nyx_light.llm.request_queue import LLMRequestQueue

        async def fake_llm(*args, **kwargs):
            return {"content": "ok"}

        async def run():
            queue = LLMRequestQueue(max_concurrent=3, max_per_minute=2)
            await queue.submit("user1", fake_llm)
            await queue.submit("user1", fake_llm)
            # user2 should still work
            result = await queue.submit("user2", fake_llm)
            assert result["content"] == "ok"

        asyncio.run(run())

    def test_stats(self):
        from nyx_light.llm.request_queue import LLMRequestQueue

        async def fake_llm(*args, **kwargs):
            return {"content": "ok"}

        async def run():
            queue = LLMRequestQueue(max_concurrent=3, max_per_minute=10)
            await queue.submit("user1", fake_llm)
            await queue.submit("user2", fake_llm)
            stats = queue.get_stats()
            assert stats["total_completed"] == 2
            assert stats["total_requests"] == 2

        asyncio.run(run())

    def test_user_stats(self):
        from nyx_light.llm.request_queue import LLMRequestQueue

        async def fake_llm(*args, **kwargs):
            return {"content": "ok"}

        async def run():
            queue = LLMRequestQueue(max_concurrent=3, max_per_minute=10)
            await queue.submit("user1", fake_llm)
            await queue.submit("user1", fake_llm)
            stats = queue.get_user_stats("user1")
            assert stats["requests"] == 2
            assert stats["completed"] == 2

        asyncio.run(run())

    def test_queue_full_error(self):
        from nyx_light.llm.request_queue import QueueFullError
        assert QueueFullError  # Just verify class exists
