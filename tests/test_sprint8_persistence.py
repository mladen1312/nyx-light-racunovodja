"""
Sprint 8 Tests: PersistentPipeline — SQLite backing for Pipeline.
"""
import os
import tempfile
import pytest
from nyx_light.pipeline import BookingProposal
from nyx_light.pipeline.persistent import PersistentPipeline


@pytest.fixture
def tmp_db():
    """Create a temporary SQLite database."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


class TestPersistentPipeline:

    def test_submit_persists(self, tmp_db):
        pp = PersistentPipeline(tmp_db)
        proposal = BookingProposal(
            client_id="K001", document_type="ulazni_racun",
            erp_target="CPP", opis="Test račun",
            lines=[{"konto": "4000", "strana": "duguje", "iznos": 1000}],
            ukupni_iznos=1000, confidence=0.9, source_module="test",
        )
        result = pp.submit(proposal)
        assert result["status"] == "pending"

        # Check SQLite
        rows = pp.db.get_pending_bookings("K001")
        assert len(rows) >= 1

    def test_approve_persists(self, tmp_db):
        pp = PersistentPipeline(tmp_db)
        proposal = BookingProposal(
            client_id="K001", document_type="ulazni_racun",
            erp_target="CPP", opis="Test", ukupni_iznos=500,
            lines=[{"konto": "4000", "strana": "duguje", "iznos": 500}],
            confidence=0.9, source_module="test",
        )
        result = pp.submit(proposal)
        pid = result["id"]

        pp.approve(pid, "ana")

        # Check in-memory
        approved = pp.get_approved("K001")
        assert len(approved) >= 1

    def test_correction_persists(self, tmp_db):
        pp = PersistentPipeline(tmp_db)
        proposal = BookingProposal(
            client_id="K001", document_type="ulazni_racun",
            erp_target="CPP", opis="Test", ukupni_iznos=500,
            lines=[{"konto": "4000", "strana": "duguje", "iznos": 500}],
            confidence=0.9, source_module="test",
        )
        result = pp.submit(proposal)
        pid = result["id"]

        pp.correct(pid, "ana", {
            "client_id": "K001",
            "original_konto": "4000",
            "corrected_konto": "4100",
            "document_type": "ulazni_racun",
        })

        corrections = pp.get_corrections_for_dpo()
        assert len(corrections) >= 1
        assert corrections[0]["original_konto"] == "4000"
        assert corrections[0]["corrected_konto"] == "4100"

    def test_stats_shows_persistent(self, tmp_db):
        pp = PersistentPipeline(tmp_db)
        stats = pp.get_stats()
        assert stats["persistent"] is True
        assert "db" in stats

    def test_reject_persists(self, tmp_db):
        pp = PersistentPipeline(tmp_db)
        proposal = BookingProposal(
            client_id="K001", document_type="ulazni_racun",
            erp_target="CPP", opis="Loš", ukupni_iznos=100,
            lines=[], confidence=0.5, source_module="test",
        )
        result = pp.submit(proposal)
        pp.reject(result["id"], "ana", "Krivi iznos")

        # No longer pending
        pending = pp.db.get_pending_bookings("K001")
        # The aggregate booking should be rejected (not pending)
        pending_ids = [r["id"] for r in pending]
        assert result["id"] not in pending_ids


class TestNyxLightAppPersistent:
    """E2E: NyxLightApp with db_path → PersistentPipeline."""

    def test_app_with_persistence(self, tmp_db):
        from nyx_light.app import NyxLightApp
        from nyx_light.registry import ClientConfig

        app = NyxLightApp(
            export_dir="/tmp/nyx_persist_test",
            db_path=tmp_db,
        )
        app.register_client(ClientConfig(
            id="PK001", naziv="Persist d.o.o.", oib="11122233344",
            erp_target="CPP",
        ))

        # Process invoice
        ocr_data = {
            "supplier": "Dobavljač", "oib": "99988877766",
            "invoice_number": "R-001", "date": "2026-01-15",
            "total": 1250.0, "pdv": 250.0, "base": 1000.0,
            "pdv_stopa": 25,
        }
        result = app.process_invoice(ocr_data, "PK001")
        assert result["status"] == "pending"

        # Approve
        app.approve(result["id"], "ana")

        # Check persistent stats
        assert app._persistent is not None
        stats = app._persistent.get_stats()
        assert stats["db"]["total_bookings"] >= 1

    def test_app_without_persistence(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp(export_dir="/tmp/nyx_no_persist")
        assert app._persistent is None
