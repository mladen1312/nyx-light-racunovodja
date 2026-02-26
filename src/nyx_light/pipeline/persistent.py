"""
Nyx Light — PersistentPipeline

Wrapper oko BookingPipeline koji:
1. Sprema svaki submit u SQLite
2. Sprema approve/reject/correct u SQLite + audit log
3. Dohvaća pending/approved iz SQLite pri restartu
4. Bilježi corrections za DPO nightly training

In-memory Pipeline ostaje BRZI radni sloj,
SQLite je TRAJNI backup koji preživljava restart sustava.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from nyx_light.pipeline import BookingPipeline, BookingProposal
from nyx_light.storage.sqlite_store import SQLiteStorage

logger = logging.getLogger("nyx_light.pipeline.persistent")


class PersistentPipeline:
    """Pipeline s SQLite persistence."""

    def __init__(self, db_path: str = "data/memory_db/nyx_light.db"):
        self.pipeline = BookingPipeline()
        self.db = SQLiteStorage(db_path)
        self._restore_from_db()
        logger.info("PersistentPipeline initialized (db: %s)", db_path)

    def _restore_from_db(self):
        """Restore pending bookings from SQLite at startup."""
        pending = self.db.get_pending_bookings()
        restored = 0
        for row in pending:
            if row["id"] not in self.pipeline._proposals:
                # Recreate minimal proposal from DB row
                self.pipeline._proposals[row["id"]] = {
                    "id": row["id"],
                    "client_id": row["client_id"],
                    "document_type": row["document_type"],
                    "status": "pending",
                    "erp_target": row.get("erp_target", "CPP"),
                    "opis": row.get("opis", ""),
                    "iznos": row.get("iznos", 0),
                    "restored_from_db": True,
                }
                restored += 1
        if restored:
            logger.info("Restored %d pending proposals from SQLite", restored)

    def submit(self, proposal: BookingProposal) -> Dict[str, Any]:
        """Submit proposal → in-memory + SQLite."""
        result = self.pipeline.submit(proposal)

        # Persist to SQLite
        for line in (proposal.lines or []):
            self.db.save_booking({
                "id": f"{result['id']}_L{line.get('r', 0)}",
                "client_id": proposal.client_id,
                "document_type": proposal.document_type,
                "konto_duguje": line.get("konto", "") if line.get("strana") == "duguje" else "",
                "konto_potrazuje": line.get("konto", "") if line.get("strana") == "potrazuje" else "",
                "iznos": line.get("iznos", 0),
                "opis": line.get("opis", proposal.opis),
                "status": "pending",
                "confidence": proposal.confidence,
                "erp_target": proposal.erp_target,
            })

        # Also save the aggregate
        self.db.save_booking({
            "id": result["id"],
            "client_id": proposal.client_id,
            "document_type": proposal.document_type,
            "iznos": proposal.ukupni_iznos,
            "opis": proposal.opis,
            "status": "pending",
            "confidence": proposal.confidence,
            "erp_target": proposal.erp_target,
        })

        return result

    def approve(self, proposal_id: str, user_id: str) -> Dict[str, Any]:
        """Approve → in-memory + SQLite."""
        result = self.pipeline.approve(proposal_id, user_id)
        self.db.approve_booking(proposal_id, user_id)
        return result

    def reject(self, proposal_id: str, user_id: str, reason: str = "") -> Dict[str, Any]:
        """Reject → in-memory + SQLite."""
        result = self.pipeline.reject(proposal_id, user_id, reason)
        self.db.reject_booking(proposal_id, user_id, reason)
        return result

    def correct(self, proposal_id: str, user_id: str, corrections: Dict) -> Dict[str, Any]:
        """Correct → in-memory + SQLite corrections table + DPO data."""
        result = self.pipeline.correct(proposal_id, user_id, corrections)

        self.db.save_correction({
            "booking_id": proposal_id,
            "user_id": user_id,
            "client_id": corrections.get("client_id", ""),
            "original_konto": corrections.get("original_konto", ""),
            "corrected_konto": corrections.get("corrected_konto", ""),
            "document_type": corrections.get("document_type", ""),
            "supplier": corrections.get("supplier", ""),
            "description": corrections.get("description", ""),
        })

        return result

    def export_approved(self, client_id: str, erp: str = "CPP",
                        fmt: str = "xml") -> Dict[str, Any]:
        """Export → in-memory pipeline + mark as exported in SQLite."""
        result = self.pipeline.export_approved(client_id, erp, fmt)

        # Mark exported in DB
        exported_ids = [b["id"] for b in result.get("bookings", [])]
        if exported_ids:
            self.db.mark_exported(exported_ids)

        return result

    def get_pending(self, client_id: str = "") -> List[Dict]:
        """Get pending from in-memory (fast path)."""
        return self.pipeline.get_pending(client_id)

    def get_approved(self, client_id: str = "") -> List[Dict]:
        """Get approved from in-memory (fast path)."""
        return self.pipeline.get_approved(client_id)

    def get_corrections_for_dpo(self) -> List[Dict]:
        """Get today's corrections for nightly DPO training."""
        return self.db.get_todays_corrections()

    def get_stats(self) -> Dict[str, Any]:
        mem_stats = self.pipeline.get_stats()
        db_stats = self.db.get_stats()
        return {
            **mem_stats,
            "db": db_stats,
            "persistent": True,
        }

    def close(self):
        self.db.close()
