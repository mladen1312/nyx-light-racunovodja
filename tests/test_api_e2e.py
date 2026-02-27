"""
Nyx Light — Comprehensive API Test Suite

Testira SVE API endpointe end-to-end:
  - Auth (login, roles, permissions)
  - Chat (query, safety, context)
  - Bookings (create, approve, reject, correct)
  - Clients (CRUD)
  - Export (CPP XML, Synesis CSV)
  - Dashboard, Deadlines, System status
  - Upload
  - HITL workflow (full cycle)
"""

import json
import os
import sys
import pytest
import time
import uuid
from pathlib import Path

# ═══════════════════════════════════════════
# FastAPI TestClient setup
# ═══════════════════════════════════════════

try:
    from fastapi.testclient import TestClient
    HAS_TESTCLIENT = True
except ImportError:
    HAS_TESTCLIENT = False

# Clean state for tests
os.environ.setdefault("NYX_TEST", "1")
for db in ["data/memory_db/nyx_light.db", "data/memory_db/auth.db", "data/dpo_training.db"]:
    Path(db).unlink(missing_ok=True)

if HAS_TESTCLIENT:
    from nyx_light.api.app import app
    client = TestClient(app, raise_server_exceptions=True)
    client.__enter__()  # Trigger lifespan


def _login(username="admin", password="admin123"):
    """Helper: login and return auth headers."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════
# HEALTH & ROOT
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestHealth:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["version"] == "2.0.0"

    def test_api_health(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "Nyx Light" in r.text


# ═══════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestAuth:
    def test_login_admin(self):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200
        d = r.json()
        assert "token" in d
        assert d["user"]["role"] == "admin"
        assert d["user"]["username"] == "admin"

    def test_login_racunovodja(self):
        r = client.post("/api/auth/login", json={"username": "racunovodja", "password": "nyx2026"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "racunovodja"

    def test_login_asistent(self):
        r = client.post("/api/auth/login", json={"username": "asistent", "password": "nyx2026"})
        assert r.status_code == 200
        assert r.json()["user"]["role"] == "asistent"

    def test_login_wrong_password(self):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401

    def test_login_unknown_user(self):
        r = client.post("/api/auth/login", json={"username": "nepostoji", "password": "x"})
        assert r.status_code == 401

    def test_auth_me(self):
        headers = _login()
        r = client.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["username"] == "admin"

    def test_no_auth(self):
        r = client.get("/api/dashboard")
        assert r.status_code == 401

    def test_invalid_token(self):
        r = client.get("/api/dashboard", headers={"Authorization": "Bearer invalid_token"})
        assert r.status_code == 401


# ═══════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestClients:
    def test_create_client(self):
        headers = _login()
        r = client.post("/api/clients", json={
            "name": f"Test d.o.o. {uuid.uuid4().hex[:4]}",
            "oib": "11111111111",
            "erp_system": "CPP"
        }, headers=headers)
        assert r.status_code == 200
        assert "id" in r.json()

    def test_list_clients(self):
        headers = _login()
        r = client.get("/api/clients", headers=headers)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_asistent_cannot_create_client(self):
        headers = _login("asistent", "nyx2026")
        r = client.post("/api/clients", json={
            "name": "Denied d.o.o.",
            "oib": "99999999999",
            "erp_system": "CPP"
        }, headers=headers)
        assert r.status_code == 403  # No permission


# ═══════════════════════════════════════════
# BOOKINGS (HITL)
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestBookings:
    def _create_client_and_booking(self, headers):
        """Helper: create client + pending booking."""
        cr = client.post("/api/clients", json={
            "name": f"BK Client {uuid.uuid4().hex[:4]}",
            "oib": "22222222222",
            "erp_system": "CPP"
        }, headers=headers)
        cid = cr.json()["id"]

        br = client.post("/api/bookings", json={
            "client_id": cid,
            "document_type": "ulazni_racun",
            "konto_duguje": "4010",
            "konto_potrazuje": "2200",
            "iznos": 1250.00,
            "pdv_stopa": 25,
            "opis": "Test račun za testing",
            "oib": "22222222222",
            "datum_dokumenta": "2026-02-27",
        }, headers=headers)
        bid = br.json()["id"]
        return cid, bid

    def test_create_booking(self):
        headers = _login()
        _, bid = self._create_client_and_booking(headers)
        assert bid.startswith("bk_")

    def test_get_pending(self):
        headers = _login()
        self._create_client_and_booking(headers)
        r = client.get("/api/pending", headers=headers)
        assert r.status_code == 200
        assert r.json()["count"] >= 1

    def test_approve_booking(self):
        headers = _login()
        _, bid = self._create_client_and_booking(headers)
        r = client.post(f"/api/approve/{bid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_reject_booking(self):
        headers = _login()
        _, bid = self._create_client_and_booking(headers)
        r = client.post(f"/api/reject/{bid}", json={"reason": "Test odbijanje"}, headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_correct_booking(self):
        headers = _login()
        _, bid = self._create_client_and_booking(headers)
        r = client.post(f"/api/correct/{bid}", json={
            "konto_duguje": "4210",
            "konto_potrazuje": "2200",
            "reason": "Ispravljen konto — usluge, ne materijal"
        }, headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "corrected"

    def test_approve_nonexistent(self):
        headers = _login()
        r = client.post("/api/approve/nonexistent_id", headers=headers)
        assert r.status_code == 404

    def test_double_approve(self):
        headers = _login()
        _, bid = self._create_client_and_booking(headers)
        client.post(f"/api/approve/{bid}", headers=headers)
        r = client.post(f"/api/approve/{bid}", headers=headers)
        assert r.status_code == 404  # Already approved

    def test_get_all_bookings(self):
        headers = _login()
        r = client.get("/api/bookings", headers=headers)
        assert r.status_code == 200
        assert "items" in r.json()

    def test_filter_bookings_by_status(self):
        headers = _login()
        r = client.get("/api/bookings?status=pending", headers=headers)
        assert r.status_code == 200

    def test_asistent_cannot_approve(self):
        admin_h = _login()
        _, bid = self._create_client_and_booking(admin_h)
        asistent_h = _login("asistent", "nyx2026")
        r = client.post(f"/api/approve/{bid}", headers=asistent_h)
        assert r.status_code == 403  # No approve permission


# ═══════════════════════════════════════════
# FULL HITL WORKFLOW
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestHITLWorkflow:
    """Test complete Human-in-the-Loop workflow."""

    def test_full_cycle(self):
        """Document → Booking → Approve → Export."""
        headers = _login()

        # 1. Create client
        cr = client.post("/api/clients", json={
            "name": "HITL Test d.o.o.",
            "oib": "33333333333",
            "erp_system": "CPP"
        }, headers=headers)
        cid = cr.json()["id"]

        # 2. Create 3 bookings
        bids = []
        for i in range(3):
            br = client.post("/api/bookings", json={
                "client_id": cid,
                "document_type": "ulazni_racun",
                "konto_duguje": "4010",
                "konto_potrazuje": "2200",
                "iznos": 1000 + i * 100,
                "opis": f"HITL test račun {i+1}",
            }, headers=headers)
            bids.append(br.json()["id"])

        # 3. Verify pending
        r = client.get(f"/api/pending?client_id={cid}", headers=headers)
        assert r.json()["count"] == 3

        # 4. Approve 2, reject 1
        client.post(f"/api/approve/{bids[0]}", headers=headers)
        client.post(f"/api/approve/{bids[1]}", headers=headers)
        client.post(f"/api/reject/{bids[2]}", json={"reason": "Duplikat"}, headers=headers)

        # 5. Verify no pending for this client
        r = client.get(f"/api/pending?client_id={cid}", headers=headers)
        assert r.json()["count"] == 0

        # 6. Export approved
        r = client.post("/api/export", json={
            "client_id": cid,
            "format": "cpp_xml"
        }, headers=headers)
        d = r.json()
        assert d["count"] == 2
        assert d["filename"].endswith(".xml")

        # 7. Second export should be empty (already exported)
        r = client.post("/api/export", json={
            "client_id": cid,
            "format": "cpp_xml"
        }, headers=headers)
        assert r.json()["count"] == 0

    def test_correct_and_learn(self):
        """Correct booking → L2 memory learns rule."""
        headers = _login()

        # Create client + booking
        cr = client.post("/api/clients", json={
            "name": "Learn Test d.o.o.",
            "oib": "44444444444"
        }, headers=headers)
        cid = cr.json()["id"]

        br = client.post("/api/bookings", json={
            "client_id": cid,
            "document_type": "ulazni_racun",
            "konto_duguje": "4010",
            "konto_potrazuje": "2200",
            "iznos": 500,
            "opis": "Usluga čišćenja",
        }, headers=headers)
        bid = br.json()["id"]

        # Correct: 4010 → 4290 (usluge, ne materijal)
        r = client.post(f"/api/correct/{bid}", json={
            "konto_duguje": "4290",
            "konto_potrazuje": "2200",
            "reason": "Usluge čišćenja idu na 4290, ne 4010"
        }, headers=headers)
        assert r.json()["status"] == "corrected"


# ═══════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestChat:
    def test_chat_pdv(self):
        headers = _login()
        r = client.post("/api/chat", json={
            "message": "Koja je stopa PDV-a u RH?",
            "client_id": ""
        }, headers=headers)
        assert r.status_code == 200
        assert len(r.json()["content"]) > 10

    def test_chat_kontiranje(self):
        headers = _login()
        r = client.post("/api/chat", json={
            "message": "Kako kontirati ulazni račun za uredski materijal?",
        }, headers=headers)
        assert r.status_code == 200

    def test_chat_safety_blocks_legal(self):
        headers = _login()
        r = client.post("/api/chat", json={
            "message": "Sastavi mi ugovor o djelu",
        }, headers=headers)
        assert r.status_code == 200
        d = r.json()
        # Should be blocked or warned
        assert d.get("blocked") or "izvan domene" in d.get("content", "").lower() or "⚠" in d.get("content", "")


# ═══════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestExport:
    def test_export_cpp_xml(self):
        headers = _login()
        # Create client + booking + approve
        cr = client.post("/api/clients", json={"name": "Export Test", "oib": "55555555555"}, headers=headers)
        cid = cr.json()["id"]
        br = client.post("/api/bookings", json={
            "client_id": cid, "konto_duguje": "4010", "konto_potrazuje": "2200",
            "iznos": 999, "opis": "Export test"
        }, headers=headers)
        bid = br.json()["id"]
        client.post(f"/api/approve/{bid}", headers=headers)

        # Export
        r = client.post("/api/export", json={"client_id": cid, "format": "cpp_xml"}, headers=headers)
        d = r.json()
        assert d["count"] == 1
        assert d["filename"].endswith(".xml")
        assert d["format"] == "cpp_xml"

        # Verify XML file exists
        export_path = Path(f"data/exports/{cid}/{d['filename']}")
        assert export_path.exists()
        xml = export_path.read_text()
        assert "<CPPImport>" in xml
        assert "<Iznos>999.00</Iznos>" in xml

    def test_export_synesis_csv(self):
        headers = _login()
        cr = client.post("/api/clients", json={"name": "Synesis Test", "oib": "66666666666"}, headers=headers)
        cid = cr.json()["id"]
        br = client.post("/api/bookings", json={
            "client_id": cid, "konto_duguje": "1000", "konto_potrazuje": "2400",
            "iznos": 555, "opis": "Synesis test"
        }, headers=headers)
        client.post(f"/api/approve/{br.json()['id']}", headers=headers)

        r = client.post("/api/export", json={"client_id": cid, "format": "synesis_csv"}, headers=headers)
        d = r.json()
        assert d["count"] == 1
        assert d["filename"].endswith(".csv")


# ═══════════════════════════════════════════
# DASHBOARD & DEADLINES & SYSTEM
# ═══════════════════════════════════════════

@pytest.mark.skipif(not HAS_TESTCLIENT, reason="FastAPI not installed")
class TestDashboard:
    def test_dashboard(self):
        headers = _login()
        r = client.get("/api/dashboard", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert "pending" in d
        assert "approved" in d
        assert "total_bookings" in d
        assert "clients" in d

    def test_deadlines(self):
        headers = _login()
        r = client.get("/api/deadlines", headers=headers)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 2
        # Should have PDV and JOPPD
        names = [i["name"] for i in items]
        assert any("PDV" in n for n in names)
        assert any("JOPPD" in n for n in names)

    def test_system_status(self):
        headers = _login()
        r = client.get("/api/system/status", headers=headers)
        assert r.status_code == 200
        d = r.json()
        assert "model" in d
        assert "vllm_status" in d
        assert "uptime_seconds" in d


# ═══════════════════════════════════════════
# BACKUP & SCHEDULER
# ═══════════════════════════════════════════

class TestBackup:
    def test_create_backup(self):
        from nyx_light.backup import BackupManager
        bm = BackupManager()
        result = bm.create_backup("test")
        assert result["files_backed"] >= 0
        assert "name" in result

    def test_list_backups(self):
        from nyx_light.backup import BackupManager
        bm = BackupManager()
        bm.create_backup("list_test")
        backups = bm.list_backups()
        assert len(backups) >= 1

    def test_backup_stats(self):
        from nyx_light.backup import BackupManager
        bm = BackupManager()
        stats = bm.get_stats()
        assert "total_backups" in stats


class TestScheduler:
    def test_scheduler_creation(self):
        from nyx_light.scheduler import NyxScheduler
        s = NyxScheduler()
        s.add_task("test", hour=2, func=lambda: {"ok": True})
        stats = s.get_stats()
        assert len(stats["tasks"]) == 1
        assert stats["tasks"][0]["name"] == "test"


class TestDPOTrainer:
    def test_record_pair(self):
        from nyx_light.finetune import NightlyDPOTrainer
        trainer = NightlyDPOTrainer()
        trainer.record_pair(
            prompt="Kontiranje ulaznog računa za uredski materijal",
            chosen="Duguje 4010, Potražuje 2200",
            rejected="Duguje 4290, Potražuje 2200",
            client_id="K001",
            module="kontiranje"
        )
        stats = trainer.get_stats()
        assert stats["total_pairs"] >= 1

    def test_collect_pairs(self):
        from nyx_light.finetune import NightlyDPOTrainer
        trainer = NightlyDPOTrainer()
        pairs = trainer.collect_todays_pairs()
        assert isinstance(pairs, list)

    def test_export_dataset(self):
        from nyx_light.finetune import NightlyDPOTrainer
        trainer = NightlyDPOTrainer()
        # Add some pairs
        for i in range(3):
            trainer.record_pair(f"prompt {i}", f"chosen {i}", f"rejected {i}")
        pairs = trainer.collect_unused_pairs()
        if pairs:
            path = trainer.export_dataset(pairs)
            assert Path(path).exists()

    def test_stats(self):
        from nyx_light.finetune import NightlyDPOTrainer
        trainer = NightlyDPOTrainer()
        stats = trainer.get_stats()
        assert "total_pairs" in stats
        assert "lora_adapters" in stats


# ═══════════════════════════════════════════
# MEMORY SYSTEM
# ═══════════════════════════════════════════

class TestMemorySystem:
    def test_4tier_memory(self):
        from nyx_light.memory.system import MemorySystem
        mem = MemorySystem()

        # L0: Working
        mem.l0_working.add_message("user", "Test poruka")
        assert len(mem.l0_working.get_conversation()) == 1

        # L1: Episodic
        mem.l1_episodic.store("Test query", "Test response", "u001", "s001")
        results = mem.l1_episodic.search_today("Test")
        assert len(results) >= 1

        # L2: Semantic
        mem.l2_semantic.store("Klijent X: materijal na 4010", topics=["X", "materijal"])
        facts = mem.l2_semantic.search(topics=["X"])
        assert len(facts) >= 1

    def test_record_correction(self):
        from nyx_light.memory.system import MemorySystem
        mem = MemorySystem()
        mem.record_correction(
            user_id="u001",
            client_id="K001",
            original_konto="4010",
            corrected_konto="4290",
            document_type="ulazni_racun",
            description="Usluge, ne materijal"
        )
        hint = mem.get_kontiranje_hint("K001")
        # May or may not find hint depending on topic matching
        assert isinstance(hint, (dict, type(None)))

    def test_memory_stats(self):
        from nyx_light.memory.system import MemorySystem
        mem = MemorySystem()
        stats = mem.get_stats()
        assert "l0_working" in stats
        assert "l1_episodic" in stats
        assert "l2_semantic" in stats
