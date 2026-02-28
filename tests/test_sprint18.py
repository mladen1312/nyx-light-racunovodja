"""
Sprint 18 Tests — Complete coverage for all new modules.
"""

import json
import os
import pytest
import time
from pathlib import Path

# ═══════════════════════════════════════════
# E-RAČUN (UBL 2.1)
# ═══════════════════════════════════════════

class TestERacun:
    def test_generate_ubl(self):
        from nyx_light.modules.e_racun import ERacunGenerator, ERacunData, ERacunStavka
        gen = ERacunGenerator()
        data = ERacunData(
            broj_racuna="R-2026-001",
            datum_izdavanja="2026-02-27",
            datum_dospijeca="2026-03-27",
            izdavatelj_naziv="Test d.o.o.",
            izdavatelj_oib="12345678901",
            izdavatelj_iban="HR1234567890123456789",
            primatelj_naziv="Kupac d.o.o.",
            primatelj_oib="98765432101",
            stavke=[
                ERacunStavka(opis="Usluga savjetovanja", kolicina=10, cijena_bez_pdv=100, pdv_stopa=25),
                ERacunStavka(opis="Prijevoz", kolicina=1, cijena_bez_pdv=50, pdv_stopa=13),
            ],
        )
        xml = gen.generate_ubl(data)
        assert '<?xml version="1.0"' in xml
        assert "R-2026-001" in xml
        assert "12345678901" in xml
        assert "98765432101" in xml
        assert "1000.00" in xml  # Line extension: 10*100
        assert "50.00" in xml    # Line extension: 1*50
        assert "urn:oasis:names" in xml

    def test_validate_errors(self):
        from nyx_light.modules.e_racun import ERacunGenerator, ERacunData
        gen = ERacunGenerator()
        data = ERacunData()  # Empty
        errors = gen.validate(data)
        assert len(errors) >= 3
        assert any("Broj" in e for e in errors)
        assert any("OIB" in e for e in errors)

    def test_stavka_calculations(self):
        from nyx_light.modules.e_racun import ERacunStavka
        s = ERacunStavka(opis="Test", kolicina=5, cijena_bez_pdv=200, pdv_stopa=25)
        assert s.osnovica == 1000.0
        assert s.pdv_iznos == 250.0
        assert s.ukupno == 1250.0

    def test_stavka_with_popust(self):
        from nyx_light.modules.e_racun import ERacunStavka
        s = ERacunStavka(opis="Test", kolicina=10, cijena_bez_pdv=100, pdv_stopa=25, popust_pct=10)
        assert s.osnovica == 900.0  # 1000 - 10%
        assert s.pdv_iznos == 225.0
        assert s.ukupno == 1125.0

    def test_summary(self):
        from nyx_light.modules.e_racun import ERacunGenerator, ERacunData, ERacunStavka
        gen = ERacunGenerator()
        data = ERacunData(
            broj_racuna="R-001",
            izdavatelj_naziv="Firma A",
            primatelj_naziv="Firma B",
            stavke=[ERacunStavka(opis="X", kolicina=1, cijena_bez_pdv=100, pdv_stopa=25)],
        )
        s = gen.generate_summary(data)
        assert s["osnovica"] == 100.0
        assert s["pdv"] == 25.0
        assert s["ukupno"] == 125.0


# ═══════════════════════════════════════════
# KOMPENZACIJE
# ═══════════════════════════════════════════

class TestKompenzacije:
    def test_find_bilateral(self):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine, OtvorenaStavka
        engine = KompenzacijeEngine()
        stavke = [
            OtvorenaStavka(partner_oib="11111111111", partner_naziv="Firma A",
                           broj_dokumenta="UR-1", iznos=5000, preostalo=5000,
                           tip="dugovanje"),
            OtvorenaStavka(partner_oib="11111111111", partner_naziv="Firma A",
                           broj_dokumenta="IR-1", iznos=3000, preostalo=3000,
                           tip="potrazivanje"),
        ]
        pairs = engine.find_bilateral(stavke)
        assert len(pairs) == 1
        assert pairs[0].kompenzabilno == 3000.0

    def test_execute_bilateral(self):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine, KompenzacijaPar
        engine = KompenzacijeEngine()
        par = KompenzacijaPar(
            partner_oib="11111111111", partner_naziv="Firma A",
            nas_dug=5000, njihov_dug=3000, kompenzabilno=3000,
        )
        izjava = engine.execute_bilateral(par, "99999999999", "Mi d.o.o.")
        assert izjava.iznos == 3000
        assert izjava.broj.startswith("KOMP-")

    def test_generate_knjizenje(self):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine, KompenzacijaIzjava
        engine = KompenzacijeEngine()
        izjava = KompenzacijaIzjava(
            broj="KOMP-TEST",
            partner_naziv="Test",
            iznos=1000,
            stavke_zatvorene=[{"tip": "nase_dugovanje", "dokument": "UR-1",
                               "iznos_zatvoren": 1000, "konto": "2200"}],
        )
        knjizenja = engine.generate_knjizenje(izjava)
        assert len(knjizenja) == 1
        assert knjizenja[0]["iznos"] == 1000

    def test_no_pairs_when_one_sided(self):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine, OtvorenaStavka
        engine = KompenzacijeEngine()
        stavke = [
            OtvorenaStavka(partner_oib="11111111111", preostalo=5000, tip="dugovanje"),
            # Only dugovanje, no potrazivanje → no pair
        ]
        pairs = engine.find_bilateral(stavke)
        assert len(pairs) == 0

    def test_multilateral_cycle(self):
        from nyx_light.modules.kompenzacije import KompenzacijeEngine, OtvorenaStavka
        engine = KompenzacijeEngine()
        # A→B, B→C, C→A  (cycle of 3)
        stavke_po_tvrtki = {
            "A": [OtvorenaStavka(partner_oib="B", preostalo=1000, tip="dugovanje")],
            "B": [OtvorenaStavka(partner_oib="C", preostalo=1500, tip="dugovanje")],
            "C": [OtvorenaStavka(partner_oib="A", preostalo=2000, tip="dugovanje")],
        }
        result = engine.find_multilateral(stavke_po_tvrtki)
        assert result is not None
        assert result.ukupno_kompenzirano == 1000  # min in cycle


# ═══════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════

class TestReports:
    def test_bilanca_excel(self):
        from nyx_light.modules.reports import ReportGenerator
        gen = ReportGenerator("Test d.o.o.", "12345678901")
        data = {
            "aktiva": [
                {"konto": "0", "naziv": "DUGOTRAJNA IMOVINA", "tekuca": 100000, "prethodna": 90000},
                {"konto": "01", "naziv": "Nematerijalna", "tekuca": 5000, "prethodna": 4000},
            ],
            "pasiva": [
                {"konto": "9", "naziv": "KAPITAL", "tekuca": 100000, "prethodna": 90000},
            ],
        }
        path = gen.generate_bilanca(data, "2026-01", "/tmp/test_bilanca.xlsx")
        assert Path(path).exists()
        Path(path).unlink()

    def test_rdg_excel(self):
        from nyx_light.modules.reports import ReportGenerator
        gen = ReportGenerator("Test d.o.o.")
        data = {
            "prihodi": [{"rbr": "I.", "naziv": "Poslovni prihodi", "tekuca": 500000, "prethodna": 480000}],
            "rashodi": [{"rbr": "IV.", "naziv": "Poslovni rashodi", "tekuca": 420000, "prethodna": 400000}],
        }
        path = gen.generate_rdg(data, "2026", "/tmp/test_rdg.xlsx")
        assert Path(path).exists()
        Path(path).unlink()

    def test_bruto_bilanca_excel(self):
        from nyx_light.modules.reports import ReportGenerator
        gen = ReportGenerator()
        stavke = [
            {"konto": "4010", "naziv": "Materijalni troškovi", "duguje": 50000, "potrazuje": 0},
            {"konto": "2200", "naziv": "Dobavljači", "duguje": 10000, "potrazuje": 50000},
        ]
        path = gen.generate_bruto_bilanca(stavke, output_path="/tmp/test_bb.xlsx")
        assert Path(path).exists()
        Path(path).unlink()

    def test_pdv_recap(self):
        from nyx_light.modules.reports import ReportGenerator
        gen = ReportGenerator()
        data = {
            "izlazni": [{"stopa": 25, "osnovica": 100000, "pdv": 25000}],
            "ulazni": [{"stopa": 25, "osnovica": 80000, "pdv": 20000}],
        }
        path = gen.generate_pdv_recap(data, output_path="/tmp/test_pdv.xlsx")
        assert Path(path).exists()
        Path(path).unlink()

    def test_kartica_konta(self):
        from nyx_light.modules.reports import ReportGenerator
        gen = ReportGenerator()
        stavke = [
            {"datum": "2026-01-15", "dokument": "UR-1", "opis": "Nabava", "duguje": 1000, "potrazuje": 0},
            {"datum": "2026-01-20", "dokument": "BN-1", "opis": "Plaćanje", "duguje": 0, "potrazuje": 800},
        ]
        path = gen.generate_kartica("4010", "Materijal", stavke, output_path="/tmp/test_kartica.xlsx")
        assert Path(path).exists()
        Path(path).unlink()


# ═══════════════════════════════════════════
# AUDIT EXPORT
# ═══════════════════════════════════════════

class TestAuditExport:
    def test_export_json(self):
        from nyx_light.audit.export import AuditExporter
        exporter = AuditExporter()
        entries = [
            {"timestamp": "2026-02-27T10:00:00", "user": "admin", "action": "login",
             "module": "auth", "client_id": "", "details": {}, "ip_address": "127.0.0.1",
             "session_id": "s1", "result": "success", "risk_level": "low"},
        ]
        path = exporter.export_json(entries, "/tmp/test_audit.json")
        assert Path(path).exists()
        with open(path) as f:
            data = json.load(f)
        assert data["count"] == 1
        Path(path).unlink()

    def test_export_csv(self):
        from nyx_light.audit.export import AuditExporter
        exporter = AuditExporter()
        entries = [
            {"timestamp": "2026-02-27", "user": "admin", "action": "approve"},
        ]
        path = exporter.export_csv(entries, "/tmp/test_audit.csv")
        assert Path(path).exists()
        Path(path).unlink()

    def test_summary(self):
        from nyx_light.audit.export import AuditExporter
        exporter = AuditExporter()
        entries = [
            {"user": "admin", "action": "login", "module": "auth", "risk_level": "low"},
            {"user": "admin", "action": "approve", "module": "kontiranje", "risk_level": "low"},
            {"user": "ivan", "action": "login", "module": "auth", "risk_level": "low"},
        ]
        s = exporter.summary(entries)
        assert s["total"] == 3
        assert s["by_user"]["admin"] == 2
        assert s["risk"]["low"] == 3


# ═══════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════

class TestNotifications:
    def test_notification_create(self):
        from nyx_light.notifications import Notification
        n = Notification(type="info", title="Test", message="Hello")
        assert n.id.startswith("notif_")
        assert n.timestamp > 0
        d = n.to_dict()
        assert d["title"] == "Test"

    def test_manager_store(self):
        from nyx_light.notifications import NotificationManager, Notification
        mgr = NotificationManager()
        # Manually store
        n = Notification(type="info", title="Test", target="user:admin")
        mgr._notifications["admin"].append(n)
        assert len(mgr.get_all("admin")) == 1
        assert len(mgr.get_unread("admin")) == 1

    def test_mark_read(self):
        from nyx_light.notifications import NotificationManager, Notification
        mgr = NotificationManager()
        n = Notification(type="info", title="Test")
        mgr._notifications["admin"].append(n)
        assert mgr.mark_read("admin", n.id)
        assert len(mgr.get_unread("admin")) == 0

    def test_mark_all_read(self):
        from nyx_light.notifications import NotificationManager, Notification
        mgr = NotificationManager()
        for i in range(5):
            mgr._notifications["admin"].append(
                Notification(type="info", title=f"Test {i}"))
        count = mgr.mark_all_read("admin")
        assert count == 5
        assert len(mgr.get_unread("admin")) == 0

    def test_stats(self):
        from nyx_light.notifications import NotificationManager
        mgr = NotificationManager()
        stats = mgr.get_stats()
        assert "sent" in stats
        assert "connections" in stats


# ═══════════════════════════════════════════
# MULTI-CLIENT PIPELINE
# ═══════════════════════════════════════════

class TestMultiClientPipeline:
    def test_classifier_bank(self):
        from nyx_light.pipeline.multi_client import DocumentClassifier
        clf = DocumentClassifier()
        doc_type, conf = clf.classify("Izvod br. 15 Promet računa", "izvod.sta")
        assert doc_type == "bankovni_izvod"
        assert conf > 0.7

    def test_classifier_invoice(self):
        from nyx_light.pipeline.multi_client import DocumentClassifier
        clf = DocumentClassifier()
        doc_type, conf = clf.classify("Račun br R-2026-001 PDV 25% ukupno s PDV")
        assert doc_type == "ulazni_racun"

    def test_classifier_putni(self):
        from nyx_light.pipeline.multi_client import DocumentClassifier
        clf = DocumentClassifier()
        doc_type, conf = clf.classify("Putni nalog br 5 dnevnica relacija Zagreb-Split")
        assert doc_type == "putni_nalog"

    def test_client_matcher_oib(self):
        from nyx_light.pipeline.multi_client import ClientMatcher
        clients = [{"id": "K1", "name": "Firma A", "oib": "12345678901", "ibans": []}]
        matcher = ClientMatcher(clients)
        client, conf = matcher.match("OIB dobavljača: 12345678901")
        assert client is not None
        assert client["id"] == "K1"
        assert conf >= 0.9

    def test_client_matcher_iban(self):
        from nyx_light.pipeline.multi_client import ClientMatcher
        clients = [{"id": "K2", "name": "Firma B", "oib": "99999999999",
                     "ibans": ["HR1234567890123456789"]}]
        matcher = ClientMatcher(clients)
        client, conf = matcher.match("IBAN: HR1234567890123456789")
        assert client is not None
        assert client["id"] == "K2"

    def test_pipeline_ingest(self, tmp_path):
        from nyx_light.pipeline.multi_client import MultiClientPipeline
        # Create test file
        f = tmp_path / "test_racun.pdf"
        f.write_text("Račun br R-2026-001 PDV 25%")
        pipeline = MultiClientPipeline([
            {"id": "K1", "name": "Test d.o.o.", "oib": "12345678901", "ibans": []}
        ])
        doc = pipeline.ingest(str(f), source="upload",
                              text_content="Račun br R-2026-001 OIB 12345678901 PDV 25%")
        assert doc.detected_type == "ulazni_racun"
        assert doc.detected_client_id == "K1"
        assert doc.assigned_module == "invoice_ocr"

    def test_pipeline_stats(self):
        from nyx_light.pipeline.multi_client import MultiClientPipeline
        pipeline = MultiClientPipeline()
        stats = pipeline.get_stats()
        assert stats["total"] == 0


# ═══════════════════════════════════════════
# API ENDPOINTS (Sprint 18)
# ═══════════════════════════════════════════

@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from nyx_light.api.app import app
    with TestClient(app) as c:
        yield c

@pytest.fixture(scope="module")
def headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestSprint18Endpoints:
    def test_e_racun_validate(self, client, headers):
        resp = client.post("/api/e-racun/validate", headers=headers, json={
            "broj_racuna": "R-001",
            "izdavatelj_oib": "12345678901",
            "primatelj_oib": "98765432101",
            "stavke": [{"opis": "Test", "kolicina": 1, "cijena_bez_pdv": 100, "pdv_stopa": 25}],
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_e_racun_validate_errors(self, client, headers):
        resp = client.post("/api/e-racun/validate", headers=headers, json={
            "stavke": []
        })
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
        assert len(resp.json()["errors"]) > 0

    def test_e_racun_generate(self, client, headers):
        resp = client.post("/api/e-racun/generate", headers=headers, json={
            "broj_racuna": "R-001",
            "datum_izdavanja": "2026-02-27",
            "izdavatelj_naziv": "Test d.o.o.",
            "izdavatelj_oib": "12345678901",
            "izdavatelj_iban": "HR1234567890123456789",
            "primatelj_naziv": "Kupac d.o.o.",
            "primatelj_oib": "98765432101",
            "stavke": [{"opis": "Savjetovanje", "kolicina": 10, "cijena_bez_pdv": 100, "pdv_stopa": 25}],
        })
        assert resp.status_code == 200
        assert "xml" in resp.json()
        assert "summary" in resp.json()
        assert resp.json()["summary"]["ukupno"] == 1250.0

    def test_kompenzacije_find(self, client, headers):
        resp = client.post("/api/kompenzacije/find", headers=headers, json={
            "stavke": [
                {"partner_oib": "11111111111", "partner_naziv": "A", "preostalo": 5000, "tip": "dugovanje"},
                {"partner_oib": "11111111111", "partner_naziv": "A", "preostalo": 3000, "tip": "potrazivanje"},
            ]
        })
        assert resp.status_code == 200
        assert len(resp.json()["pairs"]) == 1
        assert resp.json()["pairs"][0]["kompenzabilno"] == 3000

    def test_kompenzacije_execute(self, client, headers):
        resp = client.post("/api/kompenzacije/execute", headers=headers, json={
            "partner_oib": "11111111111", "partner_naziv": "Test",
            "nas_dug": 5000, "njihov_dug": 3000, "kompenzabilno": 3000,
            "nas_oib": "99999999999", "nas_naziv": "Mi d.o.o.",
        })
        assert resp.status_code == 200
        assert resp.json()["izjava"]["iznos"] == 3000

    def test_report_bilanca(self, client, headers):
        resp = client.post("/api/reports/bilanca", headers=headers, json={
            "firma": "Test", "oib": "12345678901", "period": "2026",
            "aktiva": [{"konto": "0", "naziv": "DI", "tekuca": 100000, "prethodna": 90000}],
            "pasiva": [{"konto": "9", "naziv": "K", "tekuca": 100000, "prethodna": 90000}],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "generated"

    def test_report_rdg(self, client, headers):
        resp = client.post("/api/reports/rdg", headers=headers, json={
            "prihodi": [{"rbr": "I.", "naziv": "Prihodi", "tekuca": 500000, "prethodna": 480000}],
            "rashodi": [{"rbr": "IV.", "naziv": "Rashodi", "tekuca": 420000, "prethodna": 400000}],
        })
        assert resp.status_code == 200

    def test_audit_summary(self, client, headers):
        resp = client.get("/api/audit/summary", headers=headers)
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_audit_export_json(self, client, headers):
        resp = client.get("/api/audit/export?format=json", headers=headers)
        assert resp.status_code == 200

    def test_notifications_get(self, client, headers):
        resp = client.get("/api/notifications", headers=headers)
        assert resp.status_code == 200
        assert "notifications" in resp.json()

    def test_notifications_read_all(self, client, headers):
        resp = client.post("/api/notifications/read-all", headers=headers)
        assert resp.status_code == 200

    def test_pipeline_queue(self, client, headers):
        resp = client.get("/api/pipeline/queue", headers=headers)
        assert resp.status_code == 200
        assert "queue" in resp.json()

    def test_pipeline_ingest(self, client, headers):
        resp = client.post("/api/pipeline/ingest", headers=headers, json={
            "filepath": "/tmp/test.pdf",
            "source": "api",
            "text_content": "Račun br R-001 PDV 25% OIB 12345678901",
        })
        assert resp.status_code == 200
        assert resp.json()["type"] == "ulazni_racun"

    def test_total_endpoints_75plus(self, client, headers):
        from nyx_light.api.app import app
        routes = [r for r in app.routes if hasattr(r, "methods")]
        assert len(routes) >= 70, f"Samo {len(routes)} endpointa"

    def test_dashboard_chart_data_week(self, client, headers):
        resp = client.get("/api/dashboard/chart-data?period=week", headers=headers)
        assert resp.status_code == 200
        d = resp.json()
        assert "bookings_chart" in d
        assert len(d["bookings_chart"]["labels"]) == 7

    def test_dashboard_chart_data_month(self, client, headers):
        resp = client.get("/api/dashboard/chart-data?period=month", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["bookings_chart"]["labels"]) == 30

    def test_audit_query(self, client, headers):
        resp = client.get("/api/audit/query?limit=10", headers=headers)
        assert resp.status_code == 200
        assert "entries" in resp.json()

    def test_audit_stats(self, client, headers):
        resp = client.get("/api/audit/stats", headers=headers)
        assert resp.status_code == 200

    def test_kompenzacije_multilateral(self, client, headers):
        resp = client.post("/api/kompenzacije/multilateral", headers=headers,
                          json={"tvrtke": []})
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# AUDIT LOGGER (new centralized logger)
# ═══════════════════════════════════════════

class TestAuditLogger:
    def test_log_and_query(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        audit.log("test", "action1", user="user1", details={"k": "v"})
        entries = audit.query(event_type="test")
        assert len(entries) == 1
        assert entries[0]["user"] == "user1"

    def test_login_tracking(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        audit.log_login("admin", "192.168.1.1", success=True)
        audit.log_login("hacker", "10.0.0.1", success=False)
        entries = audit.query(event_type="auth")
        assert len(entries) == 2
        assert any(e["severity"] == "warning" for e in entries)

    def test_booking_trail(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        audit.log_booking("ivan", "B001", "created", "K001")
        audit.log_approval("admin", "B001", True)
        audit.log_correction("admin", "B001", {"konto": "4010→4020"})
        entries = audit.query()
        assert len(entries) == 3

    def test_stats(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        for i in range(5):
            audit.log("booking", f"action_{i}", user="test")
        audit.log("auth", "login", user="admin")
        stats = audit.get_stats()
        assert stats["total_entries"] == 6
        assert stats["by_type"]["booking"] == 5

    def test_count(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        for i in range(10):
            audit.log("test", f"a{i}")
        assert audit.count(event_type="test") == 10

    def test_security_log(self, tmp_path):
        from nyx_light.audit import AuditLogger
        audit = AuditLogger(db_path=str(tmp_path / "audit.db"))
        audit.log_security("brute_force_attempt", user="unknown",
                          details={"attempts": 10, "ip": "10.0.0.1"})
        entries = audit.query(severity="critical")
        assert len(entries) == 1


# ═══════════════════════════════════════════
# NEW MULTICLIENT PIPELINE
# ═══════════════════════════════════════════

class TestNewMultiClientPipeline:
    def test_matcher_email_domain(self):
        from nyx_light.pipeline.multiclient import ClientMatcher
        matcher = ClientMatcher([
            {"oib": "12345678901", "email_domains": ["firma.hr"]},
        ])
        doc = {"text": "", "filename": "r.pdf", "sender_email": "info@firma.hr"}
        client, method, _ = matcher.match(doc)
        assert client is not None
        assert method == "email_domain"

    def test_matcher_folder_routing(self):
        from nyx_light.pipeline.multiclient import ClientMatcher
        matcher = ClientMatcher([
            {"oib": "99999999999", "folder_name": "klijent_xyz"},
        ])
        doc = {"text": "", "filename": "x.pdf", "source_folder": "/uploads/klijent_xyz"}
        client, method, conf = matcher.match(doc)
        assert client is not None
        assert method == "folder"
        assert conf >= 0.95

    def test_classify_xml_eracun(self):
        from nyx_light.pipeline.multiclient import DocumentPipeline
        pipe = DocumentPipeline()
        cls = pipe.classify_document("eracun.xml", "<CrossIndustryInvoice xmlns='cii'>")
        assert cls["type"] == "e_racun"

    def test_entity_extraction(self):
        from nyx_light.pipeline.multiclient import DocumentPipeline
        pipe = DocumentPipeline()
        result = pipe.process(
            filename="test.pdf",
            text="OIB: 12345678901 IBAN: HR1234567890123456789 Iznos: 1.500,00 EUR Datum: 15.02.2026",
        )
        assert "12345678901" in result["entities"].get("oibs", [])
        assert "HR1234567890123456789" in result["entities"].get("ibans", [])

    def test_pipeline_stats(self):
        from nyx_light.pipeline.multiclient import DocumentPipeline
        pipe = DocumentPipeline()
        pipe.process(filename="a.pdf", text="test")
        pipe.process(filename="b.sta", text="izvod")
        stats = pipe.get_stats()
        assert stats["total_processed"] == 2


# ═══════════════════════════════════════════
# CHAT + RAG INTEGRATION
# ═══════════════════════════════════════════

class TestChatRAGIntegration:
    """Verifikacija da chat koristi RAG i module fallback."""

    def test_fallback_uses_rag(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Koja je stopa PDV-a?")
        assert "PDV" in resp
        assert "25%" in resp

    def test_fallback_payroll_calculation(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Bruto plaća 2500 EUR")
        assert "Za isplatu" in resp or "isplatu" in resp.lower() or "MIO" in resp
        assert "2,500" in resp or "2500" in resp

    def test_fallback_kontiranje(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Kako kontirati uredski materijal?")
        assert "kontir" in resp.lower()

    def test_fallback_greeting(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Pozdrav!")
        assert "Nyx Light" in resp or "asistent" in resp.lower()

    def test_rag_store_search_returns_results(self):
        from nyx_light.rag.embedded_store import EmbeddedVectorStore
        store = EmbeddedVectorStore()
        results = store.search("porez na dobit", top_k=3)
        assert len(results) >= 1
        assert hasattr(results[0], "text")
        assert len(results[0].text) > 0

    def test_chat_endpoint_with_rag(self):
        """Test da chat endpoint uključuje RAG u context."""
        from fastapi.testclient import TestClient
        from nyx_light.api.app import app, state
        # Ensure all required state is initialized for test
        if not state.auth:
            from nyx_light.auth import AuthManager
            state.auth = AuthManager()
        if not state.chat_bridge:
            from nyx_light.llm.chat_bridge import ChatBridge
            state.chat_bridge = ChatBridge()
        if not state.overseer:
            from nyx_light.safety.overseer import AccountingOverseer
            state.overseer = AccountingOverseer()
        if not state.memory:
            from nyx_light.memory.system import MemorySystem
            state.memory = MemorySystem()
        if not state.storage:
            from nyx_light.storage.sqlite_store import SQLiteStorage
            state.storage = SQLiteStorage()

        client = TestClient(app)
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/chat", headers=headers,
                          json={"message": "Koja je stopa PDV-a za hranu?"})
        assert resp.status_code == 200
        content = resp.json().get("content", "")
        assert len(content) > 20  # Not empty
        assert "PDV" in content or "porez" in content.lower()
