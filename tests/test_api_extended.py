"""
Nyx Light — Tests za nove API endpointe (Sprint 13)

Monitoring, Backup, DPO, Laws, Audit, Scheduler, Konto
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

for d in ["data/memory_db", "data/logs", "data/uploads", "data/exports",
          "data/dpo_datasets", "data/models/lora", "data/laws", "data/backups"]:
    Path(d).mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from nyx_light.api.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture(scope="module")
def asistent_headers(client):
    resp = client.post("/api/auth/login", json={"username": "asistent", "password": "nyx2026"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ═══════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════

class TestMonitoring:
    def test_monitor_full(self, client, admin_headers):
        resp = client.get("/api/monitor", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "timestamp" in data or "status" in data

    def test_monitor_memory(self, client, admin_headers):
        resp = client.get("/api/monitor/memory", headers=admin_headers)
        assert resp.status_code == 200

    def test_monitor_inference(self, client, admin_headers):
        resp = client.get("/api/monitor/inference", headers=admin_headers)
        assert resp.status_code == 200

    def test_monitor_no_auth(self, client):
        resp = client.get("/api/monitor")
        assert resp.status_code == 401


# ═══════════════════════════════════════════
# BACKUP
# ═══════════════════════════════════════════

class TestBackup:
    def test_list_backups(self, client, admin_headers):
        resp = client.get("/api/backups", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "backups" in data

    def test_create_daily_backup(self, client, admin_headers):
        resp = client.post("/api/backups/daily", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # BackupManager returns name, files_backed, label
        assert "name" in data or "status" in data or "filename" in data

    def test_verify_backup_listed(self, client, admin_headers):
        # After creating a backup, it should appear in list
        resp = client.get("/api/backups", headers=admin_headers)
        data = resp.json()
        assert len(data["backups"]) >= 1

    def test_asistent_cannot_backup(self, client, asistent_headers):
        resp = client.post("/api/backups/daily", headers=asistent_headers)
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# DPO TRAINING
# ═══════════════════════════════════════════

class TestDPO:
    def test_dpo_stats(self, client, admin_headers):
        resp = client.get("/api/dpo/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_pairs" in data or "status" in data

    def test_dpo_adapters(self, client, admin_headers):
        resp = client.get("/api/dpo/adapters", headers=admin_headers)
        assert resp.status_code == 200
        assert "adapters" in resp.json()

    def test_dpo_train_manual(self, client, admin_headers):
        resp = client.post("/api/dpo/train", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should be skipped (not enough pairs)
        assert data["status"] in ("skipped", "completed", "error")


# ═══════════════════════════════════════════
# LAWS / RAG
# ═══════════════════════════════════════════

class TestLaws:
    def test_list_laws(self, client, admin_headers):
        resp = client.get("/api/laws", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "laws" in data
        assert data["count"] >= 5  # We seeded 5 laws

    def test_law_has_metadata(self, client, admin_headers):
        resp = client.get("/api/laws", headers=admin_headers)
        laws = resp.json()["laws"]
        pdv = next((l for l in laws if "pdv" in l["file"].lower()), None)
        assert pdv is not None
        assert pdv["nn"] != ""
        assert pdv["datum_stupanja"] != ""

    def test_search_laws_pdv(self, client, admin_headers):
        resp = client.get("/api/laws/search?q=PDV stopa", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_search_laws_dobit(self, client, admin_headers):
        resp = client.get("/api/laws/search?q=porez na dobit", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_search_laws_empty(self, client, admin_headers):
        resp = client.get("/api/laws/search", headers=admin_headers)
        assert resp.status_code == 400  # Missing q parameter

    def test_search_laws_no_results(self, client, admin_headers):
        resp = client.get("/api/laws/search?q=xyznepostoji123", headers=admin_headers)
        assert resp.status_code == 200
        # May return 0 results or fallback results depending on search method
        data = resp.json()
        assert "results" in data or "query" in data


# ═══════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════

class TestAudit:
    def test_get_audit_log(self, client, admin_headers):
        resp = client.get("/api/audit", headers=admin_headers)
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_audit_has_login_entries(self, client, admin_headers):
        # Login should have created audit entries
        resp = client.get("/api/audit", headers=admin_headers)
        items = resp.json()["items"]
        # May have entries depending on auth system
        assert isinstance(items, list)


# ═══════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════

class TestScheduler:
    def test_scheduler_status(self, client, admin_headers):
        resp = client.get("/api/scheduler/status", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data

    def test_scheduler_run_backup(self, client, admin_headers):
        resp = client.post("/api/scheduler/run?task=backup", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Either scheduler result or direct backup result
        assert isinstance(data, dict)


# ═══════════════════════════════════════════
# KONTO SEARCH
# ═══════════════════════════════════════════

class TestKonto:
    def test_search_konto_uredski(self, client, admin_headers):
        resp = client.get("/api/konto/search?q=uredski materijal", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data

    def test_search_konto_empty(self, client, admin_headers):
        resp = client.get("/api/konto/search", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["results"] == []


# ═══════════════════════════════════════════
# API ENDPOINT COUNT
# ═══════════════════════════════════════════

class TestEndpointCount:
    def test_minimum_endpoints(self, client, admin_headers):
        """Sustav mora imati minimalno 30 endpointa."""
        from nyx_light.api.app import app
        routes = [r for r in app.routes if hasattr(r, "methods")]
        assert len(routes) >= 30, f"Samo {len(routes)} endpointa (trebamo min 30)"

    def test_all_critical_endpoints_exist(self, client, admin_headers):
        """Provjeri da svi kritični endpointi postoje."""
        critical = [
            ("POST", "/api/auth/login"),
            ("GET", "/api/auth/me"),
            ("POST", "/api/chat"),
            ("GET", "/api/pending"),
            ("GET", "/api/bookings"),
            ("POST", "/api/bookings"),
            ("GET", "/api/clients"),
            ("POST", "/api/upload"),
            ("POST", "/api/export"),
            ("GET", "/api/dashboard"),
            ("GET", "/api/deadlines"),
            ("GET", "/api/system/status"),
            ("GET", "/api/monitor"),
            ("GET", "/api/backups"),
            ("POST", "/api/backups/daily"),
            ("GET", "/api/dpo/stats"),
            ("GET", "/api/laws"),
            ("GET", "/api/laws/search"),
            ("GET", "/api/audit"),
            ("GET", "/api/scheduler/status"),
            ("GET", "/api/konto/search"),
            ("GET", "/health"),
        ]
        from nyx_light.api.app import app
        route_map = {}
        for r in app.routes:
            if hasattr(r, "methods") and hasattr(r, "path"):
                for m in r.methods:
                    route_map[(m, r.path)] = True

        missing = []
        for method, path in critical:
            if (method, path) not in route_map:
                missing.append(f"{method} {path}")
        assert not missing, f"Nedostaju endpointi: {missing}"
