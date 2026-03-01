"""
Sprint 27: DPO End-to-End + WebSocket Module Cards

Verificira:
1. DPO pair recording: approve → pair, correct → pair, reject → pair
2. DPO trainer wired into scheduler
3. DPO API endpoints use state.dpo_trainer
4. Module card builder za svaki tip modula
5. WebSocket handler šalje module_card prije tokena
6. Frontend WS connection + card rendering
7. Frontend stream-bubble CSS
"""

import json
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch


# ═══════════════════════════════════════════
# DPO E2E Pipeline Tests
# ═══════════════════════════════════════════

class TestDPOPairRecording:
    """Test da approve/correct/reject kreiraju DPO parove."""

    def test_dpo_trainer_init(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-init-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        stats = trainer.get_stats()
        assert "total_pairs" in stats
        assert "unused_pairs" in stats
        assert "ready_for_training" in stats
        shutil.rmtree(d, ignore_errors=True)

    def test_record_pair(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-rec-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        trainer.record_pair(
            prompt="Kontiranje: Uredski materijal | Tip: URA | Iznos: 1250",
            chosen="Duguje: 4010 | Potražuje: 2200",
            rejected="Duguje: 4090 | Potražuje: 2200",
            client_id="K001",
            module="kontiranje",
            correction_type="corrected",
        )
        stats = trainer.get_stats()
        assert stats["total_pairs"] >= 1
        assert stats["unused_pairs"] >= 1
        shutil.rmtree(d, ignore_errors=True)

    def test_collect_unused_pairs(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-coll-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        for i in range(5):
            trainer.record_pair(
                prompt=f"Test prompt {i}",
                chosen=f"Chosen {i}",
                rejected=f"Rejected {i}",
            )
        pairs = trainer.collect_unused_pairs()
        assert len(pairs) == 5
        shutil.rmtree(d, ignore_errors=True)

    def test_export_dataset(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-exp-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        for i in range(3):
            trainer.record_pair(
                prompt=f"Prompt {i}", chosen=f"Good {i}", rejected=f"Bad {i}",
            )
        pairs = trainer.collect_unused_pairs()
        path = trainer.export_dataset(pairs)
        assert Path(path).exists()
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert "prompt" in first
        assert "chosen" in first
        assert "rejected" in first
        shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_train_nightly_skipped_insufficient(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-skip-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        # Only 3 pairs, need 10
        for i in range(3):
            trainer.record_pair(prompt=f"P{i}", chosen=f"C{i}", rejected=f"R{i}")
        result = await trainer.train_nightly()
        assert result["status"] == "skipped"
        shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_train_nightly_with_enough_pairs(self):
        import shutil
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-dpo-train-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        for i in range(15):
            trainer.record_pair(prompt=f"P{i}", chosen=f"C{i}", rejected=f"R{i}")
        result = await trainer.train_nightly()
        # Will be "skipped_no_mlx" since MLX isn't available in container
        assert result["status"] in ("completed", "skipped_no_mlx")
        assert result["pairs_used"] == 15
        # Verify pairs marked as used
        stats = trainer.get_stats()
        assert stats["unused_pairs"] == 0
        shutil.rmtree(d, ignore_errors=True)


class TestDPOSchedulerWiring:
    """Test da scheduler ima DPO task."""

    def test_setup_default_scheduler_with_dpo(self):
        import shutil
        from nyx_light.scheduler import setup_default_scheduler
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        d = f"/tmp/nyx-test-sched-{int(__import__('time').time())}"
        trainer = NightlyDPOTrainer(data_dir=d)
        scheduler = setup_default_scheduler(dpo_trainer=trainer)
        task_names = [t.name for t in scheduler.tasks]
        assert "nightly_dpo" in task_names

        dpo_task = [t for t in scheduler.tasks if t.name == "nightly_dpo"][0]
        assert dpo_task.hour == 2
        assert dpo_task.minute == 0
        assert dpo_task.func is not None
        shutil.rmtree(d, ignore_errors=True)

    def test_scheduler_has_backup_task(self):
        from nyx_light.scheduler import setup_default_scheduler
        backup = MagicMock()
        scheduler = setup_default_scheduler(backup_manager=backup)
        task_names = [t.name for t in scheduler.tasks]
        assert "nightly_backup" in task_names


class TestDPOApiEndpoints:
    """Test da DPO API endpoints koriste state.dpo_trainer."""

    def test_dpo_endpoints_use_state(self):
        import inspect
        from nyx_light.api.app import dpo_stats, dpo_adapters, dpo_train_manual
        for fn in [dpo_stats, dpo_adapters, dpo_train_manual]:
            source = inspect.getsource(fn)
            assert "state.dpo_trainer" in source, \
                f"{fn.__name__} should use state.dpo_trainer"
            # Should NOT create new NightlyDPOTrainer instance
            assert "NightlyDPOTrainer()" not in source, \
                f"{fn.__name__} should NOT create new trainer"

    def test_dpo_history_endpoint_exists(self):
        from nyx_light.api.app import app
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/dpo/history" in paths

    def test_scheduler_status_endpoint_exists(self):
        from nyx_light.api.app import app
        paths = {r.path for r in app.routes if hasattr(r, "path")}
        assert "/api/scheduler/status" in paths


# ═══════════════════════════════════════════
# Module Card Builder Tests
# ═══════════════════════════════════════════

class TestModuleCardBuilder:
    """Test _build_module_card za svaki tip modula."""

    def _build(self, module, data, summary="Test"):
        from nyx_light.api.app import _build_module_card
        return _build_module_card(module, "", data, summary)

    def test_kontiranje_card(self):
        card = self._build("kontiranje", {
            "konto_duguje": "4010", "konto_potrazuje": "2200",
            "pdv_konto": "1400", "confidence": 0.92,
            "alternativni": [{"duguje": "4090", "potrazuje": "2200"}],
        })
        assert card is not None
        assert card["type"] == "konto"
        assert len(card["rows"]) >= 3
        assert card["confidence"] == 0.92
        assert len(card["alternatives"]) == 1

    def test_blagajna_card_ok(self):
        card = self._build("blagajna", {
            "iznos": 500, "limit_ok": True, "valid": True, "novi_saldo": 1500,
        })
        assert card["type"] == "validation"
        assert card["status"] == "success"
        assert any("OK" in r["value"] for r in card["rows"])

    def test_blagajna_card_error(self):
        card = self._build("blagajna", {
            "iznos": 15000, "limit_ok": False, "valid": False,
        })
        assert card["status"] == "error"
        assert any("PREKORAČEN" in r["value"] for r in card["rows"])

    def test_payroll_card(self):
        card = self._build("place", {
            "bruto": 2500, "neto": 1660, "za_isplatu": 1550,
            "mio_1": 500, "zdravstveno": 412.5, "porez": 180,
        })
        assert card["type"] == "payroll"
        assert len(card["rows"]) >= 4

    def test_pdv_card(self):
        card = self._build("pdv_prijava", {
            "pretporez": 5000, "obveza": 8000, "razlika": 3000,
        })
        assert card["type"] == "tax"
        assert len(card["rows"]) == 3

    def test_porez_dobit_card(self):
        card = self._build("porez_dobit", {
            "dobit": 100000, "stopa": 18, "porez": 18000,
        })
        assert card["type"] == "tax"
        assert any("18%" in r["value"] for r in card["rows"])

    def test_putni_nalog_card(self):
        card = self._build("putni_nalozi", {
            "dnevnice": 53.08, "km_naknada": 120, "ukupno": 173.08,
        })
        assert card["type"] == "travel"
        assert len(card["rows"]) == 3

    def test_deadlines_card(self):
        card = self._build("deadlines", {"items": [
            {"name": "PDV", "due_date": "2026-03-20", "days_remaining": 5},
            {"name": "JOPPD", "due_date": "2026-03-15", "days_remaining": 2},
        ]})
        assert card["type"] == "list"
        assert len(card["items"]) == 2
        assert card["items"][1]["urgent"]  # 2 days

    def test_bank_card(self):
        card = self._build("bank_parser", {"transactions": [
            {"datum": "2026-01-15", "opis": "Plaćanje računa", "iznos": -500},
            {"datum": "2026-01-16", "opis": "Uplata", "iznos": 3000},
        ], "count": 2})
        assert card["type"] == "table"
        assert len(card["rows_table"]) == 2
        assert card["headers"] == ["Datum", "Opis", "Iznos"]

    def test_joppd_card(self):
        card = self._build("joppd", {
            "tip": "plaća", "mjesec": "2026-01", "status": "generirano",
        })
        assert card is not None
        assert card["type"] == "generic"
        assert len(card["rows"]) >= 3

    def test_gfi_card(self):
        card = self._build("gfi_xml", {
            "godina": 2025, "tip": "bilanca", "status": "generirano",
        })
        assert card is not None
        assert card["type"] == "generic"

    def test_generic_card(self):
        card = self._build("amortizacija", {
            "stopa": 25, "grupa": 2, "godisnji_iznos": 2500,
        })
        assert card["type"] == "generic"
        assert len(card["rows"]) == 3

    def test_none_data_returns_none(self):
        card = self._build("kontiranje", None, "Test")
        assert card is None

    def test_empty_data_returns_none(self):
        card = self._build("kontiranje", {}, "Test")
        assert card is None


class TestModuleCardInWsHandler:
    """Test da WS handler šalje module_card."""

    def test_ws_handler_has_module_card(self):
        import inspect
        from nyx_light.api.app import ws_chat
        source = inspect.getsource(ws_chat)
        assert "module_card" in source
        assert "_build_module_card" in source

    def test_card_sent_before_tokens(self):
        """Verify card is sent BEFORE LLM streaming starts."""
        import inspect
        from nyx_light.api.app import ws_chat
        source = inspect.getsource(ws_chat)
        card_pos = source.index("module_card")
        token_pos = source.index("chat_stream")
        assert card_pos < token_pos, "Card must be sent before streaming"


# ═══════════════════════════════════════════
# Frontend Tests
# ═══════════════════════════════════════════

class TestFrontendModuleCards:
    """Test frontend WS + card rendering code."""

    def _html(self):
        with open("static/index.html") as f:
            return f.read()

    def test_ws_connect_function(self):
        html = self._html()
        assert "function connectChatWs" in html
        assert "new WebSocket" in html
        assert "module_card" in html

    def test_ws_connected_on_login(self):
        html = self._html()
        assert "connectChatWs()" in html

    def test_ws_disconnected_on_logout(self):
        html = self._html()
        assert "_chatWs.close()" in html or "chatWs.close" in html

    def test_render_module_card_function(self):
        html = self._html()
        assert "function renderModuleCard" in html
        assert "mc-header" in html
        assert "mc-module" in html
        assert "mc-konto" in html

    def test_stream_bubble(self):
        html = self._html()
        assert "stream-bubble" in html
        assert "_appendStreamToken" in html
        assert "_finishStream" in html

    def test_module_card_css(self):
        html = self._html()
        required_css = [
            ".module-card", ".mc-header", ".mc-module", ".mc-conf",
            ".mc-row", ".mc-icon", ".mc-label", ".mc-value", ".mc-konto",
            ".mc-table", ".mc-urgent", ".mc-error",
        ]
        for cls in required_css:
            assert cls in html, f"Missing CSS: {cls}"

    def test_card_types_handled(self):
        """Verify frontend handles all card types."""
        html = self._html()
        for card_type in ["konto", "table", "list"]:
            assert f"card.type==='{card_type}'" in html or f"type==='{card_type}'" in html, \
                f"Frontend missing handler for card type: {card_type}"


class TestDPOCorrectEndpointWiring:
    """Test da correct endpoint zapisuje DPO par."""

    def test_correct_endpoint_has_dpo(self):
        import inspect
        from nyx_light.api.app import correct
        source = inspect.getsource(correct)
        assert "dpo_trainer" in source
        assert "record_pair" in source
        assert "correction_type" in source

    def test_approve_endpoint_has_dpo(self):
        import inspect
        from nyx_light.api.app import approve
        source = inspect.getsource(approve)
        assert "dpo_trainer" in source
        assert "record_pair" in source

    def test_reject_endpoint_has_dpo(self):
        import inspect
        from nyx_light.api.app import reject
        source = inspect.getsource(reject)
        assert "dpo_trainer" in source
        assert "record_pair" in source


class TestProductionHardening:
    """Test middleware i exception handlers."""

    def test_request_logging_middleware(self):
        import inspect
        from nyx_light.api.app import request_logging_middleware
        source = inspect.getsource(request_logging_middleware)
        assert "/api/" in source
        assert "duration" in source.lower() or "start" in source

    def test_global_exception_handler(self):
        import inspect
        from nyx_light.api.app import global_exception_handler
        source = inspect.getsource(global_exception_handler)
        assert "500" in source
        # Response must not include traceback info
        assert "traceback" not in source.split('"""')[-1].lower()
        assert "Interna greška" in source

    def test_cors_configurable(self):
        import inspect
        from nyx_light.api import app as app_module
        source = inspect.getsource(app_module)
        assert "NYX_ALLOWED_ORIGINS" in source
