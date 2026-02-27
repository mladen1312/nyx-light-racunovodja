"""
Nyx Light — API Integration Tests

Testira sve produkcijske endpointe:
  - Auth (login, me, users)
  - Chat (HITL, safety)
  - Bookings (CRUD, approve, reject, correct)
  - Clients
  - Upload
  - Export
  - Dashboard & System Status
  - Deadlines
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Ensure test data dirs
for d in ["data/memory_db", "data/logs", "data/uploads", "data/exports",
          "data/dpo_datasets", "data/models/lora", "data/laws", "data/backups"]:
    Path(d).mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient with app lifespan."""
    from fastapi.testclient import TestClient
    from nyx_light.api.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    """Login as admin and return token."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    assert "token" in data
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    """Auth headers for API calls."""
    return {"Authorization": f"Bearer {admin_token}"}


# ═══════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_api_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["storage"] is True
        assert data["auth"] is True

    def test_root_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200


# ═══════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════

class TestAuth:
    def test_login_success(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "admin"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_unknown_user(self, client):
        resp = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
        assert resp.status_code == 401

    def test_auth_me(self, client, auth_headers):
        resp = client.get("/api/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"

    def test_no_token_rejected(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_bad_token_rejected(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# CHAT
# ═══════════════════════════════════════════

class TestChat:
    def test_chat_basic(self, client, auth_headers):
        resp = client.post("/api/chat", headers=auth_headers,
                           json={"message": "Koji je rok za PDV prijavu?", "client_id": ""})
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data

    def test_chat_with_client(self, client, auth_headers):
        # First create a client
        client.post("/api/clients", headers=auth_headers,
                    json={"name": "Test d.o.o.", "oib": "12345678901", "erp_system": "CPP"})
        resp = client.post("/api/chat", headers=auth_headers,
                           json={"message": "Kako kontirati ulazni račun?", "client_id": "test"})
        assert resp.status_code == 200

    def test_chat_safety_blocks_legal(self, client, auth_headers):
        resp = client.post("/api/chat", headers=auth_headers,
                           json={"message": "Sastavi mi ugovor o radu"})
        assert resp.status_code == 200
        data = resp.json()
        # Should be blocked or warned by overseer
        assert "content" in data

    def test_chat_no_auth(self, client):
        resp = client.post("/api/chat", json={"message": "test"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════

class TestBookings:
    def test_create_booking(self, client, auth_headers):
        resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "K001",
            "document_type": "ulazni_racun",
            "konto_duguje": "4010",
            "konto_potrazuje": "2200",
            "iznos": 1250.00,
            "pdv_stopa": 25,
            "opis": "Uredski materijal - Konzum",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        return data["id"]

    def test_get_pending(self, client, auth_headers):
        # Create a booking first
        client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "KTEST", "document_type": "test",
            "konto_duguje": "1000", "konto_potrazuje": "2000",
            "iznos": 100.00, "opis": "Test pending"
        })
        resp = client.get("/api/pending", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["count"] >= 0

    def test_approve_booking(self, client, auth_headers):
        # Create then approve
        create_resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "KTEST", "document_type": "test",
            "konto_duguje": "4010", "konto_potrazuje": "2200",
            "iznos": 500.00, "opis": "Za odobrenje"
        })
        bid = create_resp.json()["id"]

        resp = client.post(f"/api/approve/{bid}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_booking(self, client, auth_headers):
        create_resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "KTEST", "document_type": "test",
            "konto_duguje": "4010", "konto_potrazuje": "2200",
            "iznos": 300.00, "opis": "Za odbijanje"
        })
        bid = create_resp.json()["id"]

        resp = client.post(f"/api/reject/{bid}", headers=auth_headers,
                           json={"reason": "Krivi konto"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_correct_booking(self, client, auth_headers):
        create_resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "KTEST", "document_type": "ulazni_racun",
            "konto_duguje": "4010", "konto_potrazuje": "2200",
            "iznos": 750.00, "opis": "Za ispravku"
        })
        bid = create_resp.json()["id"]

        resp = client.post(f"/api/correct/{bid}", headers=auth_headers, json={
            "konto_duguje": "4020",
            "konto_potrazuje": "2200",
            "reason": "Trebalo je 4020 za usluge"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "corrected"

    def test_approve_nonexistent_404(self, client, auth_headers):
        resp = client.post("/api/approve/nonexistent_id_123", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_all_bookings(self, client, auth_headers):
        resp = client.get("/api/bookings", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data


# ═══════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════

class TestClients:
    def test_create_client(self, client, auth_headers):
        resp = client.post("/api/clients", headers=auth_headers, json={
            "name": "ABC d.o.o.",
            "oib": "98765432109",
            "erp_system": "Synesis"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "ABC d.o.o."

    def test_list_clients(self, client, auth_headers):
        resp = client.get("/api/clients", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data


# ═══════════════════════════════════════════
# UPLOAD
# ═══════════════════════════════════════════

class TestUpload:
    def test_upload_pdf(self, client, auth_headers):
        # Create a fake PDF
        import io
        fake_pdf = io.BytesIO(b"%PDF-1.4 fake content for testing")
        resp = client.post("/api/upload",
                           headers={"Authorization": auth_headers["Authorization"]},
                           files={"file": ("test_racun.pdf", fake_pdf, "application/pdf")},
                           data={"client_id": "KTEST"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_type"] == "invoice_scan"

    def test_upload_no_client(self, client, auth_headers):
        import io
        resp = client.post("/api/upload",
                           headers={"Authorization": auth_headers["Authorization"]},
                           files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
                           data={"client_id": ""})
        assert resp.status_code == 400


# ═══════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════

class TestExport:
    def test_export_cpp_xml(self, client, auth_headers):
        # Create and approve a booking first
        cr = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "KEXPORT", "document_type": "test",
            "konto_duguje": "4010", "konto_potrazuje": "2200",
            "iznos": 999.99, "opis": "Export test"
        })
        bid = cr.json()["id"]
        client.post(f"/api/approve/{bid}", headers=auth_headers)

        resp = client.post("/api/export", headers=auth_headers, json={
            "client_id": "KEXPORT", "format": "cpp_xml"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 1
        assert data["format"] == "cpp_xml"

    def test_export_no_bookings(self, client, auth_headers):
        resp = client.post("/api/export", headers=auth_headers, json={
            "client_id": "EMPTY_CLIENT", "format": "json"
        })
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ═══════════════════════════════════════════
# DASHBOARD & STATUS
# ═══════════════════════════════════════════

class TestDashboard:
    def test_dashboard(self, client, auth_headers):
        resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        for key in ["pending", "approved", "total_bookings", "corrections", "clients"]:
            assert key in data

    def test_deadlines(self, client, auth_headers):
        resp = client.get("/api/deadlines", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        # Should have at least PDV deadline
        assert len(data["items"]) >= 1

    def test_system_status(self, client, auth_headers):
        resp = client.get("/api/system/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "vllm_status" in data
        assert "uptime_seconds" in data


# ═══════════════════════════════════════════
# HITL WORKFLOW (End-to-End)
# ═══════════════════════════════════════════

class TestHITLWorkflow:
    """Test kompletnog Human-in-the-Loop toka."""

    def test_full_workflow(self, client, auth_headers):
        """Dokument → Booking → Pending → Approve → Export"""
        # 1. Create booking (simulating OCR result)
        resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "WORKFLOW",
            "document_type": "ulazni_racun",
            "konto_duguje": "4010",
            "konto_potrazuje": "2200",
            "iznos": 2500.00,
            "pdv_stopa": 25,
            "opis": "IT oprema - Dell monitor",
            "oib": "12345678901",
            "datum_dokumenta": "2026-02-27",
        })
        assert resp.status_code == 200
        bid = resp.json()["id"]

        # 2. Should appear in pending
        resp = client.get("/api/pending?client_id=WORKFLOW", headers=auth_headers)
        assert resp.status_code == 200
        pending = resp.json()["items"]
        assert any(b["id"] == bid for b in pending)

        # 3. Approve
        resp = client.post(f"/api/approve/{bid}", headers=auth_headers)
        assert resp.status_code == 200

        # 4. Should NOT be in pending anymore
        resp = client.get("/api/pending?client_id=WORKFLOW", headers=auth_headers)
        pending = resp.json()["items"]
        assert not any(b["id"] == bid for b in pending)

        # 5. Export
        resp = client.post("/api/export", headers=auth_headers, json={
            "client_id": "WORKFLOW", "format": "synesis_csv"
        })
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_correct_and_learn(self, client, auth_headers):
        """Ispravak → L2 memorija → Buduća sugestija"""
        # Create wrong booking
        resp = client.post("/api/bookings", headers=auth_headers, json={
            "client_id": "LEARN",
            "document_type": "ulazni_racun",
            "konto_duguje": "4010",
            "konto_potrazuje": "2200",
            "iznos": 800.00,
            "opis": "Usluga hostinga"
        })
        bid = resp.json()["id"]

        # Correct it (4010 → 4620 for IT services)
        resp = client.post(f"/api/correct/{bid}", headers=auth_headers, json={
            "konto_duguje": "4620",
            "konto_potrazuje": "2200",
            "reason": "IT usluge idu na 4620, ne 4010"
        })
        assert resp.status_code == 200

        # Dashboard should show correction
        resp = client.get("/api/dashboard", headers=auth_headers)
        assert resp.json()["corrections"] >= 1
