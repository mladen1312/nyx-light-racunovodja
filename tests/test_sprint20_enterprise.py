"""
Sprint 20 Tests — Enterprise Grade Accounting Modules
═════════════════════════════════════════════════════
Tests for:
  1. Double-Entry Ledger (invarianti)
  2. Fiskalizacija 2.0 (KPD, HR-FISK, status kodovi)
  3. Audit Trail (immutable chain)
  4. Anomaly Detection (duplikati, Benford, IBAN)
  5. GDPR Data Masking
  6. Scalability (capacity planning)
"""

import pytest
from decimal import Decimal


# ═══════════════════════════════════════════════
# 1. DOUBLE-ENTRY LEDGER
# ═══════════════════════════════════════════════

class TestDoubleEntryLedger:
    """Striktni invarianti — srce accounting sustava."""

    def setup_method(self):
        from nyx_light.modules.ledger import GeneralLedger, Transaction, LedgerEntry, Strana
        self.GL = GeneralLedger
        self.Transaction = Transaction
        self.LedgerEntry = LedgerEntry
        self.Strana = Strana
        self.ledger = GeneralLedger()

    def test_balanced_transaction_books(self):
        """Uravnotežena transakcija se uspješno knjiži."""
        tx = self.Transaction(
            datum="2026-02-28", opis="Ulazni račun — uredski materijal",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("100.00")),
                self.LedgerEntry(konto="1230", strana=self.Strana.DUGUJE, iznos=Decimal("25.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("125.00")),
            ]
        )
        result = self.ledger.book(tx, user="ana.horvat")
        assert result.is_balanced
        assert result.status.value == "proknjizeno"
        assert result.total_duguje == Decimal("125.00")
        assert result.total_potrazuje == Decimal("125.00")

    def test_unbalanced_transaction_rejected(self):
        """Neuravnotežena transakcija se ODBIJA — ključni invariant."""
        from nyx_light.modules.ledger import BalanceError
        tx = self.Transaction(
            datum="2026-02-28", opis="Kriva transakcija",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("100.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("99.00")),
            ]
        )
        with pytest.raises(BalanceError):
            self.ledger.book(tx)

    def test_single_entry_rejected(self):
        """Samo jedna strana — odbijeno."""
        from nyx_light.modules.ledger import BalanceError
        tx = self.Transaction(
            datum="2026-02-28", opis="Samo duguje",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("100.00")),
            ]
        )
        with pytest.raises(BalanceError):
            self.ledger.book(tx)

    def test_zero_amount_rejected(self):
        """Nulti iznos — odbijeno."""
        tx = self.Transaction(
            datum="2026-02-28", opis="Nulti iznos",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("0.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("0.00")),
            ]
        )
        with pytest.raises(ValueError, match="ne smije biti 0"):
            self.ledger.book(tx)

    def test_negative_amount_rejected(self):
        """Negativni iznos — odbijeno na razini LedgerEntry."""
        with pytest.raises(ValueError, match="negativan"):
            self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("-50.00"))

    def test_trial_balance_always_balanced(self):
        """Pokusna bilanca je uvijek uravnotežena nakon validnih knjiženja."""
        # Knjiženje 1: Ulazni račun
        self.ledger.book(self.Transaction(
            datum="2026-01-15", opis="Račun 1",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("500.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("500.00")),
            ]
        ), user="test")
        # Knjiženje 2: Plaćanje
        self.ledger.book(self.Transaction(
            datum="2026-01-20", opis="Plaćanje",
            entries=[
                self.LedgerEntry(konto="2200", strana=self.Strana.DUGUJE, iznos=Decimal("500.00")),
                self.LedgerEntry(konto="1000", strana=self.Strana.POTRAZUJE, iznos=Decimal("500.00")),
            ]
        ), user="test")

        tb = self.ledger.trial_balance()
        assert tb["balanced"] == True
        assert tb["total_duguje"] == tb["total_potrazuje"]

    def test_storno_creates_reverse_entries(self):
        """Storno kreira obrnute stavke."""
        tx = self.ledger.book(self.Transaction(
            datum="2026-02-01", opis="Za storno",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos=Decimal("200.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("200.00")),
            ]
        ), user="test")

        storno = self.ledger.storno(tx.tx_id, user="test", razlog="Krivi iznos")
        assert storno.is_balanced
        assert storno.source == "storno"
        # After storno, net effect is zero
        tb = self.ledger.trial_balance()
        assert tb["balanced"] == True

    def test_ai_propose_then_approve(self):
        """AI predlaže → računovođa odobrava → proknjiži."""
        tx = self.Transaction(
            datum="2026-02-28", opis="AI prijedlog kontiranja",
            entries=[
                self.LedgerEntry(konto="4120", strana=self.Strana.DUGUJE, iznos=Decimal("1000.00")),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos=Decimal("1000.00")),
            ]
        )
        proposed = self.ledger.propose(tx)
        assert proposed.status.value == "prijedlog"

        booked = self.ledger.approve(proposed.tx_id, user="marko.k")
        assert booked.status.value == "proknjizeno"
        assert booked.created_by == "marko.k"

    def test_decimal_precision(self):
        """Koristimo Decimal, ne float — nema floating point grešaka."""
        tx = self.Transaction(
            datum="2026-02-28", opis="Precision test",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos="33.33"),
                self.LedgerEntry(konto="4020", strana=self.Strana.DUGUJE, iznos="33.33"),
                self.LedgerEntry(konto="4030", strana=self.Strana.DUGUJE, iznos="33.34"),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos="100.00"),
            ]
        )
        result = self.ledger.book(tx, user="test")
        assert result.is_balanced
        assert result.total_duguje == Decimal("100.00")

    def test_fingerprint_uniqueness(self):
        """Svaka transakcija ima unikatan fingerprint."""
        tx1 = self.Transaction(
            datum="2026-02-28", opis="TX 1",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos="100.00"),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos="100.00"),
            ]
        )
        tx2 = self.Transaction(
            datum="2026-02-28", opis="TX 2",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos="100.00"),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos="100.00"),
            ]
        )
        assert tx1.fingerprint() != tx2.fingerprint()

    def test_integrity_check(self):
        """Verifikacija integriteta nakon knjiženja."""
        self.ledger.book(self.Transaction(
            datum="2026-02-28", opis="Test",
            entries=[
                self.LedgerEntry(konto="4010", strana=self.Strana.DUGUJE, iznos="250.00"),
                self.LedgerEntry(konto="2200", strana=self.Strana.POTRAZUJE, iznos="250.00"),
            ]
        ), user="test")
        integrity = self.ledger.verify_integrity()
        assert integrity["integrity_ok"] == True
        assert integrity["global_balance"] == True


# ═══════════════════════════════════════════════
# 2. FISKALIZACIJA 2.0
# ═══════════════════════════════════════════════

class TestFiskalizacija2:
    """EN 16931 + HR-FISK + KPD 2025."""

    def setup_method(self):
        from nyx_light.modules.fiskalizacija2 import (
            Fiskalizacija2Engine, FiskRacun, FiskStavka, classify_kpd
        )
        self.engine = Fiskalizacija2Engine()
        self.FiskRacun = FiskRacun
        self.FiskStavka = FiskStavka
        self.classify_kpd = classify_kpd

    def _make_racun(self, **kwargs) -> "FiskRacun":
        defaults = dict(
            broj_racuna="FISK-2026-001",
            poslovni_prostor="PP1",
            naplatni_uredaj="NU1",
            redni_broj=1,
            datum_izdavanja="2026-02-28",
            datum_dospijeca="2026-03-30",
            izdavatelj_naziv="Test d.o.o.",
            izdavatelj_oib="12345678901",
            izdavatelj_adresa="Ilica 1",
            izdavatelj_grad="Zagreb",
            izdavatelj_postanski="10000",
            izdavatelj_iban="HR1234567890123456789",
            primatelj_naziv="Kupac d.o.o.",
            primatelj_oib="98765432109",
            primatelj_adresa="Savska 10",
            primatelj_grad="Zagreb",
            primatelj_postanski="10000",
            stavke=[self.FiskStavka(
                opis="IT konzalting usluge",
                kolicina=10,
                jedinica="sat",
                cijena_bez_pdv=100.0,
                pdv_stopa=25,
            )],
        )
        defaults.update(kwargs)
        return self.FiskRacun(**defaults)

    def test_kpd_auto_classification(self):
        """KPD kod se automatski dodjeljuje."""
        code, name, conf = self.classify_kpd("IT konzalting usluge za implementaciju softvera")
        assert len(code) == 6
        assert code == "620200"  # IT konzalting
        assert conf > 0.3

    def test_kpd_gorivo(self):
        """KPD za gorivo."""
        code, name, conf = self.classify_kpd("Gorivo benzin INA")
        assert code == "192000"

    def test_kpd_racunovodstvo(self):
        """KPD za računovodstvene usluge."""
        code, name, conf = self.classify_kpd("Računovodstvene usluge za mjesec veljaču")
        assert code == "692000"

    def test_fisk_stavka_auto_kpd(self):
        """FiskStavka automatski dodijeli KPD ako nije zadan."""
        stavka = self.FiskStavka(opis="Programiranje web aplikacije", cijena_bez_pdv=500)
        assert stavka.kpd_kod == "620100"

    def test_fisk_stavka_uom_mapping(self):
        """Mapiranje HR jedinica na UN/CEFACT."""
        stavka = self.FiskStavka(opis="Test", jedinica="sat", cijena_bez_pdv=100)
        assert stavka.jedinica == "HUR"

    def test_generate_xml_valid(self):
        """Generiraj validan UBL 2.1 XML s HR-FISK ekstenzijama."""
        racun = self._make_racun()
        xml = self.engine.generate_xml(racun)

        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" in xml
        assert "urn:cen.eu:en16931:2017" in xml
        assert "urn:fina.hr:einvoice:1.0" in xml
        assert "12345678901" in xml  # Izdavatelj OIB
        assert "98765432109" in xml  # Primatelj OIB

    def test_xml_contains_kpd_code(self):
        """XML sadrži KPD 2025 klasifikacijski kod."""
        racun = self._make_racun()
        xml = self.engine.generate_xml(racun)
        assert "KPD_2025" in xml
        assert "620200" in xml  # IT konzalting KPD

    def test_xml_contains_hr_fisk_extensions(self):
        """XML sadrži HR-FISK nacionalne ekstenzije."""
        racun = self._make_racun()
        xml = self.engine.generate_xml(racun)
        assert "FiskalizacijaData" in xml
        assert "PoslovniProstor" in xml
        assert "NaplatniUredaj" in xml
        assert "RedniBroj" in xml
        assert "PP1" in xml  # Poslovni prostor

    def test_validation_missing_oib(self):
        """Validacija odbija račun bez OIB-a."""
        racun = self._make_racun(izdavatelj_oib="123")  # Premalo znamenki
        errors = self.engine.validate(racun)
        assert any("OIB" in e for e in errors)

    def test_validation_missing_kpd(self):
        """Validacija odbija stavku bez KPD koda."""
        stavka = self.FiskStavka(opis="Test", cijena_bez_pdv=100, kpd_kod="")
        # Auto-assign will set it, but if we force empty:
        stavka.kpd_kod = ""
        racun = self._make_racun(stavke=[stavka])
        errors = self.engine.validate(racun)
        assert any("KPD" in e for e in errors)

    def test_ack_status_10_accepted(self):
        """Status 10 = uspješno fiskalizirano."""
        result = self.engine.process_ack("10", invoice_id="INV-001")
        assert result["action"] == "PROKNJIZI"

    def test_ack_status_90_xml_error(self):
        """Status 90 = XML greška → AI analiza."""
        result = self.engine.process_ack("90", "Missing KPD classification", "INV-002")
        assert result["action"] == "AI_ANALIZA"
        assert "KPD" in result["ai_suggestion"]

    def test_ack_status_91_cert_error(self):
        """Status 91 = certifikat greška."""
        result = self.engine.process_ack("91", "Invalid signature", "INV-003")
        assert result["action"] == "PROVJERI_CERTIFIKAT"
        assert len(result["checks"]) >= 3

    def test_ack_status_99_retry(self):
        """Status 99 = retry s exponential backoff."""
        result = self.engine.process_ack("99", "Service unavailable", "INV-004")
        assert result["action"] == "RETRY"
        assert result["max_retries"] == 5

    def test_receive_invoice(self):
        """Zaprimanje ulaznog e-računa — rok 5 radnih dana."""
        result = self.engine.receive_invoice(sender_oib="11111111111")
        assert result["days_remaining"] == 5
        assert "approve" in result["actions_available"]
        assert "reject" in result["actions_available"]

    def test_sign_invoice(self):
        """Potpis računa generira hash."""
        racun = self._make_racun()
        xml = self.engine.generate_xml(racun)
        signed = self.engine.sign_invoice(xml)
        assert signed["signed"] == True
        assert len(signed["content_hash"]) == 64  # SHA-256

    def test_strukturirani_broj(self):
        """PP/NU/RB format."""
        racun = self._make_racun()
        assert racun.strukturirani_broj == "PP1/NU1/1"


# ═══════════════════════════════════════════════
# 3. AUDIT TRAIL
# ═══════════════════════════════════════════════

class TestAuditTrail:
    """Immutable chain-linked audit log."""

    def setup_method(self):
        from nyx_light.modules.audit import AuditTrail, AkcijaTip, RizikRazina
        self.trail = AuditTrail()
        self.AkcijaTip = AkcijaTip
        self.RizikRazina = RizikRazina

    def test_log_entry(self):
        """Osnovno logiranje."""
        entry = self.trail.log(
            user_id="ana.h", action=self.AkcijaTip.KNJIZENJE,
            module="ledger", details="Proknjižen ulazni račun",
        )
        assert entry.fingerprint != ""
        assert entry.user_id == "ana.h"

    def test_chain_integrity(self):
        """Lanac hashova je validan."""
        for i in range(5):
            self.trail.log("user1", self.AkcijaTip.KNJIZENJE,
                          "ledger", f"Entry {i}")
        result = self.trail.verify_chain()
        assert result["valid"] == True
        assert result["entries"] == 5

    def test_ai_vs_human_actions(self):
        """Jasno razdvajanje AI i ljudskih akcija."""
        self.trail.log("AI_SYSTEM", self.AkcijaTip.AI_PRIJEDLOG,
                      "kontiranje", "AI predložio konto 4120")
        self.trail.log("marko.k", self.AkcijaTip.ODOBRENJE,
                      "kontiranje", "Odobrio prijedlog bez korekcije")

        entries = self.trail.query()
        assert len(entries) == 2
        assert entries[0]["action"] in ("ai_prijedlog", "odobrenje")

    def test_risk_filtering(self):
        """Filtriranje po razini rizika."""
        self.trail.log("user1", self.AkcijaTip.KNJIZENJE,
                      "ledger", "Normal", risk_level=self.RizikRazina.LOW)
        self.trail.log("user2", self.AkcijaTip.KNJIZENJE,
                      "ledger", "Risky", risk_level=self.RizikRazina.HIGH)

        high = self.trail.query(risk_level="high")
        assert len(high) == 1


# ═══════════════════════════════════════════════
# 4. ANOMALY DETECTION
# ═══════════════════════════════════════════════

class TestAnomalyDetection:
    """Detekcija prijevara i grešaka."""

    def setup_method(self):
        from nyx_light.modules.audit import AnomalyDetector
        self.detector = AnomalyDetector()

    def test_duplicate_detection(self):
        """Detektira duplicirano plaćanje."""
        # Prvo plaćanje
        self.detector.check_transaction(
            iznos=5000, partner_oib="12345678901", datum="2026-02-20")
        # Duplikat unutar 7 dana
        anomalies = self.detector.check_transaction(
            iznos=5000, partner_oib="12345678901", datum="2026-02-22")
        assert any(a.tip == "DUPLIKAT" for a in anomalies)

    def test_high_amount_warning(self):
        """Upozorenje za visoke iznose."""
        anomalies = self.detector.check_transaction(iznos=75000)
        assert any(a.tip == "VISOKI_IZNOS" for a in anomalies)

    def test_aml_cash_threshold(self):
        """AML prag za gotovinske transakcije."""
        anomalies = self.detector.check_transaction(
            iznos=15000, konto="1000")  # Konto klase 10 = blagajna
        assert any(a.tip == "AML_PRAG" for a in anomalies)
        assert any(a.razina.value == "critical" for a in anomalies)

    def test_iban_change_detection(self):
        """Detektira promjenu IBAN-a dobavljača."""
        self.detector.check_transaction(
            iznos=100, partner_oib="99999999999", partner_iban="HR1234567890123456789")
        anomalies = self.detector.check_transaction(
            iznos=100, partner_oib="99999999999", partner_iban="HR9876543210987654321")
        assert any(a.tip == "IBAN_PROMJENA" for a in anomalies)
        assert any(a.razina.value == "critical" for a in anomalies)

    def test_night_entry_detection(self):
        """Detektira unos izvan radnog vremena."""
        anomalies = self.detector.check_transaction(
            iznos=100, datum="2026-02-28T02:30:00")
        assert any(a.tip == "NOCNI_UNOS" for a in anomalies)

    def test_benford_law(self):
        """Benfordov zakon na batchu transakcija."""
        import random
        random.seed(42)
        # Normalna distribucija — trebala bi proći Benford test
        transactions = [
            {"iznos": random.lognormvariate(5, 2)} for _ in range(100)
        ]
        result = self.detector.check_batch(transactions)
        assert result["benford_analysis"]["applicable"] == True

    def test_batch_check(self):
        """Batch provjera s rizik sažetkom."""
        result = self.detector.check_batch([
            {"iznos": 5000, "partner_oib": "111", "datum": "2026-02-20"},
            {"iznos": 5000, "partner_oib": "111", "datum": "2026-02-21"},
            {"iznos": 75000},
        ])
        assert result["anomalies_found"] > 0
        assert "risk_summary" in result


# ═══════════════════════════════════════════════
# 5. GDPR DATA MASKING
# ═══════════════════════════════════════════════

class TestDataMasking:
    """Anonimizacija osjetljivih podataka."""

    def setup_method(self):
        from nyx_light.modules.audit import DataMasker
        self.masker = DataMasker

    def test_mask_oib(self):
        assert self.masker.mask_oib("12345678901") == "********901"

    def test_mask_iban(self):
        result = self.masker.mask_iban("HR1234567890123456789")
        assert result.startswith("HR12")
        assert result.endswith("6789")
        assert "*" in result

    def test_mask_name(self):
        assert self.masker.mask_name("Ana Horvat") == "A. H."

    def test_mask_dict(self):
        data = {"izdavatelj_oib": "12345678901", "izdavatelj_naziv": "Test d.o.o."}
        masked = self.masker.mask_dict(data)
        assert "12345678901" not in masked["izdavatelj_oib"]
        assert "Test d.o.o." not in masked["izdavatelj_naziv"]


# ═══════════════════════════════════════════════
# 6. SCALABILITY & CAPACITY
# ═══════════════════════════════════════════════

class TestScalability:
    """Kapacitetno planiranje i skalabilnost."""

    def test_capacity_report_192gb(self):
        from nyx_light.modules.scalability import capacity_report
        report = capacity_report("target_192gb")
        assert report["max_concurrent_users"] == 20
        assert report["sqlite_sufficient"] == True

    def test_capacity_report_64gb(self):
        from nyx_light.modules.scalability import capacity_report
        report = capacity_report("target_64gb")
        assert report["max_concurrent_users"] == 5

    def test_personnel_analysis(self):
        """AI smanjuje potrebu za zaposlenicima."""
        from nyx_light.modules.scalability import capacity_report
        report = capacity_report("target_192gb")
        analysis = report["treba_li_vise_zaposlenika"]
        assert "NE" in analysis["odgovor"]
        assert analysis["s_ai_sustavom"]["klijenti_po_racunovodji"] > \
               analysis["bez_ai"]["klijenti_po_racunovodji"]

    def test_connection_pool(self):
        from nyx_light.modules.scalability import ConnectionPool
        pool = ConnectionPool(":memory:", max_connections=5)
        conn = pool.acquire()
        assert conn is not None
        pool.release(conn)
        stats = pool.get_stats()
        assert stats["total_requests"] == 1

    def test_accuracy_monitor(self):
        from nyx_light.modules.scalability import AccuracyMonitor
        monitor = AccuracyMonitor()
        monitor.log_proposal("kontiranje")
        monitor.log_approved("kontiranje")
        monitor.log_proposal("kontiranje")
        monitor.log_corrected("kontiranje")

        acc = monitor.get_accuracy("kontiranje")
        assert acc["kontiranje"]["accuracy_pct"] == 50.0  # 1 approved / 2 total


# ═══════════════════════════════════════════════
# 7. INTEGRATION TESTS
# ═══════════════════════════════════════════════

class TestFiskalizacijaLedgerIntegration:
    """Integracija Fiskalizacije 2.0 s Ledgerom."""

    def test_fisk_to_ledger_flow(self):
        """E-račun → fiskalizacija → auto knjiženje u ledger."""
        from nyx_light.modules.fiskalizacija2 import (
            Fiskalizacija2Engine, FiskRacun, FiskStavka)
        from nyx_light.modules.ledger import (
            GeneralLedger, Transaction, LedgerEntry, Strana)

        # 1. Kreiraj e-račun
        fisk = Fiskalizacija2Engine()
        racun = FiskRacun(
            broj_racuna="2026-001",
            poslovni_prostor="PP1", naplatni_uredaj="NU1", redni_broj=1,
            datum_izdavanja="2026-02-28",
            izdavatelj_naziv="Naša firma", izdavatelj_oib="11111111111",
            primatelj_naziv="Kupac", primatelj_oib="22222222222",
            stavke=[FiskStavka(opis="IT konzalting", kolicina=10,
                              jedinica="sat", cijena_bez_pdv=100, pdv_stopa=25)],
        )

        # 2. Generiraj XML
        xml = fisk.generate_xml(racun)
        assert "KPD_2025" in xml

        # 3. Simuliraj ACK=10 (accepted)
        ack = fisk.process_ack("10", invoice_id="2026-001")
        assert ack["action"] == "PROKNJIZI"

        # 4. Proknjiži u ledger
        ledger = GeneralLedger()
        tx = Transaction(
            datum="2026-02-28",
            opis=f"Izlazni račun {racun.broj_racuna}",
            document_ref=racun.broj_racuna,
            entries=[
                LedgerEntry(konto="1200", strana=Strana.DUGUJE,
                           iznos=str(racun.ukupno_za_platiti), opis="Potraživanje od kupca"),
                LedgerEntry(konto="7510", strana=Strana.POTRAZUJE,
                           iznos=str(racun.ukupna_osnovica), opis="Prihod od usluga"),
                LedgerEntry(konto="2400", strana=Strana.POTRAZUJE,
                           iznos=str(racun.ukupni_pdv), opis="Obveza za PDV"),
            ]
        )
        booked = ledger.book(tx, user="system")
        assert booked.is_balanced
        assert booked.status.value == "proknjizeno"

        # 5. Trial balance check
        tb = ledger.trial_balance()
        assert tb["balanced"] == True
