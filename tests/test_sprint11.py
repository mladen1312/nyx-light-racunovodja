"""
Tests — Sprint 11: Svi novi moduli.
Auth, ModelManager, ChatBridge, E2, E3, G2, G4, DPO
"""
import os
import tempfile
import pytest
from datetime import date


# ═══════════════════════════════════════════════════
# AUTH TESTS
# ═══════════════════════════════════════════════════

class TestPasswordHashing:
    def test_hash_and_verify(self):
        from nyx_light.auth import hash_password, verify_password
        pw = "test_password_123"
        h = hash_password(pw)
        assert verify_password(pw, h) is True
        assert verify_password("wrong", h) is False

    def test_different_salts(self):
        from nyx_light.auth import hash_password
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # Different salts


class TestJWT:
    def test_create_and_decode(self):
        from nyx_light.auth import create_jwt, decode_jwt
        secret = "test_secret_123"
        payload = {"sub": "user1", "role": "admin"}
        token = create_jwt(payload, secret)
        decoded = decode_jwt(token, secret)
        assert decoded is not None
        assert decoded["sub"] == "user1"
        assert decoded["role"] == "admin"

    def test_invalid_secret(self):
        from nyx_light.auth import create_jwt, decode_jwt
        token = create_jwt({"sub": "x"}, "secret1")
        assert decode_jwt(token, "secret2") is None

    def test_expired_token(self):
        from nyx_light.auth import create_jwt, decode_jwt
        token = create_jwt({"sub": "x"}, "s", expires_hours=-1)
        assert decode_jwt(token, "s") is None


class TestAuthManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = os.path.join(self.tmpdir, "auth.db")
        from nyx_light.auth import AuthManager
        self.mgr = AuthManager(db_path=self.db)

    def test_default_admin_created(self):
        result = self.mgr.login("admin", "admin")
        assert result["ok"] is True
        assert result["user"]["role"] == "admin"
        assert "token" in result

    def test_login_wrong_password(self):
        result = self.mgr.login("admin", "wrong")
        assert result["ok"] is False

    def test_login_unknown_user(self):
        result = self.mgr.login("nobody", "pass")
        assert result["ok"] is False

    def test_create_user(self):
        from nyx_light.auth import Role
        user = self.mgr.create_user("ana", "lozinka123", "Ana K.", Role.RACUNOVODJA)
        assert user is not None
        result = self.mgr.login("ana", "lozinka123")
        assert result["ok"] is True
        assert result["user"]["role"] == "racunovodja"

    def test_duplicate_user(self):
        from nyx_light.auth import Role
        self.mgr.create_user("dup", "x", "Dup", Role.ASISTENT)
        second = self.mgr.create_user("dup", "y", "Dup2", Role.ASISTENT)
        assert second is None

    def test_permissions(self):
        result = self.mgr.login("admin", "admin")
        token = result["token"]
        assert self.mgr.has_permission(token, "manage_users") is True
        assert self.mgr.has_permission(token, "approve") is True

    def test_asistent_no_approve(self):
        from nyx_light.auth import Role
        self.mgr.create_user("asist", "pass", "Asist", Role.ASISTENT)
        result = self.mgr.login("asist", "pass")
        assert self.mgr.has_permission(result["token"], "approve") is False
        assert self.mgr.has_permission(result["token"], "chat") is True

    def test_lockout_after_failed(self):
        from nyx_light.auth import Role
        self.mgr.create_user("test", "correct", "Test", Role.ASISTENT)
        for _ in range(5):
            self.mgr.login("test", "wrong")
        result = self.mgr.login("test", "correct")
        assert result["ok"] is False  # Locked
        assert "zaključan" in result["error"].lower()

    def test_audit_log(self):
        self.mgr.login("admin", "admin")
        self.mgr.login("admin", "wrong")
        log = self.mgr.get_audit_log()
        assert len(log) >= 2
        actions = {e["action"] for e in log}
        assert "login_success" in actions
        assert "login_failed" in actions

    def test_change_password(self):
        self.mgr.change_password("admin", "new_pass")
        assert self.mgr.login("admin", "admin")["ok"] is False
        assert self.mgr.login("admin", "new_pass")["ok"] is True

    def test_list_users(self):
        users = self.mgr.list_users()
        assert len(users) >= 1
        assert users[0].username == "admin"


# ═══════════════════════════════════════════════════
# MODEL MANAGER TESTS
# ═══════════════════════════════════════════════════

class TestModelManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from nyx_light.model_manager import ModelManager
        self.mgr = ModelManager(
            models_dir=os.path.join(self.tmpdir, "models"),
            config_path=os.path.join(self.tmpdir, "models", "registry.json"),
        )

    def test_detect_ram(self):
        ram = self.mgr.detect_ram_gb()
        assert ram >= 0

    def test_recommend_model_192(self):
        spec = self.mgr.recommend_model(192)
        assert "235" in spec.name or "72" in spec.name

    def test_recommend_model_96(self):
        spec = self.mgr.recommend_model(96)
        assert "72" in spec.name

    def test_recommend_model_64(self):
        spec = self.mgr.recommend_model(64)
        assert "32" in spec.name.lower() or "R1" in spec.name

    def test_status(self):
        status = self.mgr.get_status()
        assert "ram_gb" in status
        assert "installed_models" in status

    def test_verify_knowledge(self):
        result = self.mgr.verify_knowledge_intact()
        assert "all_intact" in result
        assert "paths" in result

    def test_catalog_has_models(self):
        from nyx_light.model_manager import MODEL_CATALOG
        assert len(MODEL_CATALOG) >= 4
        assert "qwen2.5-vl-7b" in MODEL_CATALOG


# ═══════════════════════════════════════════════════
# CHAT BRIDGE TESTS
# ═══════════════════════════════════════════════════

class TestChatBridge:
    def test_build_messages(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        msgs = bridge.build_messages("Kako kontirati nabavu?", "sess1")
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert "kontirati" in msgs[-1]["content"]

    def test_build_messages_with_context(self):
        from nyx_light.llm.chat_bridge import ChatBridge, ChatContext
        bridge = ChatBridge()
        ctx = ChatContext(
            rag_results=[{"source": "ZoPDV čl.5", "text": "Porezni obveznik..."}],
            semantic_facts=["Klijent X koristi konto 4000 za usluge"],
            client_info={"name": "Firma d.o.o.", "oib": "12345678901"},
        )
        msgs = bridge.build_messages("PDV pitanje", "sess2", ctx)
        # Should have system + context + user = at least 3
        assert len(msgs) >= 3
        ctx_msg = msgs[1]["content"]
        assert "KONTEKST" in ctx_msg
        assert "ZoPDV" in ctx_msg

    def test_history_tracking(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        bridge.build_messages("Pitanje 1", "sess3")
        # Simulate adding history manually
        from nyx_light.llm.chat_bridge import ChatMessage
        bridge._histories["sess3"] = [
            ChatMessage("user", "Pitanje 1"),
            ChatMessage("assistant", "Odgovor 1"),
        ]
        msgs = bridge.build_messages("Pitanje 2", "sess3")
        # Should include history
        assert any("Pitanje 1" in m["content"] for m in msgs)

    def test_clear_history(self):
        from nyx_light.llm.chat_bridge import ChatBridge, ChatMessage
        bridge = ChatBridge()
        bridge._histories["sess4"] = [ChatMessage("user", "test")]
        bridge.clear_history("sess4")
        assert "sess4" not in bridge._histories

    def test_stats(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        stats = bridge.get_stats()
        assert "total_queries" in stats

    def test_fallback_response(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Kako obračunati PDV?")
        assert "PDV" in resp
        resp2 = bridge._fallback_response("Kontiranje nabave")
        assert "kontir" in resp2.lower()


# ═══════════════════════════════════════════════════
# E2: REPORT EXPLAINER TESTS
# ═══════════════════════════════════════════════════

class TestReportExplainer:
    def setup_method(self):
        from nyx_light.modules.communication import ReportExplainer
        self.exp = ReportExplainer()

    def test_bilanca_healthy(self):
        exp = self.exp.explain_bilanca({
            "aktiva_ukupno": 1000000,
            "pasiva_ukupno": 1000000,
            "kapital": 600000,
            "obveze_ukupno": 400000,
            "kratkorocne_obveze": 200000,
            "kratkotrajna_imovina": 500000,
        }, "2025")
        assert exp.title
        assert exp.summary
        assert len(exp.key_points) > 0
        assert exp.detail_level == "standard"

    def test_bilanca_indebted(self):
        exp = self.exp.explain_bilanca({
            "aktiva_ukupno": 1000000,
            "obveze_ukupno": 800000,
            "kapital": 200000,
        })
        assert any("zaduženost" in w.lower() for w in exp.warnings)

    def test_bilanca_negative_capital(self):
        exp = self.exp.explain_bilanca({"kapital": -50000, "aktiva_ukupno": 100000})
        assert any("negativan" in w.lower() for w in exp.warnings)

    def test_rdg_profit(self):
        exp = self.exp.explain_rdg({
            "prihodi_ukupno": 500000,
            "rashodi_ukupno": 400000,
        })
        assert "dobit" in exp.summary.lower()
        assert any("100" in p for p in exp.key_points)

    def test_rdg_loss(self):
        exp = self.exp.explain_rdg({
            "prihodi_ukupno": 300000,
            "rashodi_ukupno": 400000,
        })
        assert "gubitak" in exp.summary.lower()

    def test_pdv(self):
        exp = self.exp.explain_pdv({
            "pretporez_ukupno": 10000,
            "obveza_ukupno": 25000,
        })
        assert "15" in exp.summary  # 25000-10000

    def test_to_text(self):
        exp = self.exp.explain_bilanca({"aktiva_ukupno": 500000, "kapital": 300000})
        text = self.exp.to_text(exp)
        assert "📊" in text
        assert len(text) > 50


# ═══════════════════════════════════════════════════
# E3: CLIENT ONBOARDING TESTS
# ═══════════════════════════════════════════════════

class TestClientOnboarding:
    def _make_valid_oib(self, first10="1234567890"):
        a = 10
        for d in first10:
            a = (a + int(d)) % 10
            if a == 0: a = 10
            a = (a * 2) % 11
        ctrl = 11 - a
        if ctrl == 10: ctrl = 0
        return first10 + str(ctrl)

    def setup_method(self):
        from nyx_light.modules.client_management import ClientOnboarding
        self.ob = ClientOnboarding()

    def test_start_onboarding(self):
        oib = self._make_valid_oib()
        result = self.ob.start_onboarding(oib, "Test d.o.o.")
        assert result["ok"] is True
        assert result["client_id"].startswith("K")
        assert result["checklist"]["total"] > 5

    def test_invalid_oib(self):
        result = self.ob.start_onboarding("12345678900", "Bad")
        assert result["ok"] is False
        assert "OIB" in result["error"]

    def test_checklist_progress(self):
        oib = self._make_valid_oib("9876543210")
        result = self.ob.start_onboarding(oib, "Firma d.o.o.")
        cid = result["client_id"]
        self.ob.mark_doc_received(cid, "OIB potvrda")
        status = self.ob.get_checklist_status(cid)
        assert status["completed"] == 1
        assert status["progress_pct"] > 0

    def test_pausalni_obrt_no_pdv(self):
        oib = self._make_valid_oib("5555555550")
        result = self.ob.start_onboarding(oib, "Mali obrt", tip="pausalni_obrt")
        profile = result["profile"]
        assert profile["pdv_obveznik"] is False

    def test_list_clients(self):
        oib = self._make_valid_oib("1111111110")
        self.ob.start_onboarding(oib, "A d.o.o.")
        clients = self.ob.list_clients()
        assert len(clients) >= 1


# ═══════════════════════════════════════════════════
# G2: MANAGEMENT ACCOUNTING TESTS
# ═══════════════════════════════════════════════════

class TestManagementAccounting:
    def setup_method(self):
        from nyx_light.modules.management_accounting import ManagementAccounting
        self.ma = ManagementAccounting()

    def test_break_even(self):
        result = self.ma.break_even(
            fiksni_troskovi=100000,
            cijena_po_jedinici=50,
            varijabilni_po_jedinici=30,
        )
        assert result["ok"] is True
        assert result["break_even_jedinice"] == 5000  # 100k / 20 = 5000
        assert result["break_even_prihod"] == 250000

    def test_break_even_impossible(self):
        result = self.ma.break_even(100000, 30, 50)  # Cijena < var. troškovi
        assert result["ok"] is False

    def test_segments(self):
        self.ma.add_segment("Usluge", 200000, 80000, 50000)
        self.ma.add_segment("Trgovina", 300000, 250000, 30000)
        result = self.ma.analyze_segments()
        assert result["ok"] is True
        assert len(result["segments"]) == 2
        assert result["segments"][0]["segment"] == "Usluge"  # Veća dobit

    def test_abc_analysis(self):
        items = [("Klijent A", 50000), ("Klijent B", 30000),
                 ("Klijent C", 10000), ("Klijent D", 5000),
                 ("Klijent E", 3000), ("Klijent F", 2000)]
        result = self.ma.abc_analysis(items)
        assert "Klijent A" in result["A"]
        assert len(result["C"]) > 0

    def test_budget_vs_actual(self):
        self.ma.set_budget("2025-01", [
            {"konto": "4000", "naziv": "Usluge", "budget": 10000, "actual": 12000},
            {"konto": "4010", "naziv": "Materijal", "budget": 5000, "actual": 4000},
        ])
        result = self.ma.budget_vs_actual("2025-01")
        assert result["ok"] is True
        assert result["items_over_budget"] == 1
        assert result["total_variance"] == 1000

    def test_cost_centers(self):
        self.ma.add_cost("IT", "Hardware", 5000)
        self.ma.add_cost("IT", "Software", 3000)
        self.ma.add_cost("HR", "Plaće", 20000)
        report = self.ma.cost_center_report()
        assert report["centers"]["IT"]["total"] == 8000
        assert report["grand_total"] == 28000


# ═══════════════════════════════════════════════════
# G4: BUSINESS PLAN TESTS
# ═══════════════════════════════════════════════════

class TestBusinessPlan:
    def setup_method(self):
        from nyx_light.modules.business_plan import BusinessPlanGenerator
        self.bp = BusinessPlanGenerator()

    def test_projections_5_years(self):
        result = self.bp.generate_projections(
            start_year=2026, years=5,
            prihodi_y1=100000, rashodi_y1=80000,
            growth_prihodi=0.10, growth_rashodi=0.05,
        )
        assert len(result["projections"]) == 5
        assert result["projections"][0]["year"] == 2026
        assert result["summary"]["total_prihodi"] > 500000

    def test_roi_with_investment(self):
        result = self.bp.generate_projections(
            start_year=2026, years=5,
            prihodi_y1=200000, rashodi_y1=150000,
            investicija=100000,
        )
        assert result["summary"]["roi_pct"] > 0
        assert result["summary"]["payback_year"] is not None

    def test_scenario_analysis(self):
        result = self.bp.scenario_analysis(
            start_year=2026,
            prihodi_y1=100000, rashodi_y1=80000,
        )
        assert "optimistični" in result["scenarios"]
        assert "bazni" in result["scenarios"]
        assert "pesimistični" in result["scenarios"]
        opt = result["scenarios"]["optimistični"]["summary"]["total_dobit"]
        pes = result["scenarios"]["pesimistični"]["summary"]["total_dobit"]
        assert opt > pes

    def test_loan_feasibility_ok(self):
        result = self.bp.loan_feasibility(
            iznos_kredita=100000,
            kamatna_stopa=5.0,
            godine_otplate=5,
            godisnji_cashflow=30000,
        )
        assert result["feasible"] is True
        assert result["dscr"] >= 1.25

    def test_loan_feasibility_risky(self):
        result = self.bp.loan_feasibility(
            iznos_kredita=500000,
            kamatna_stopa=8.0,
            godine_otplate=5,
            godisnji_cashflow=50000,
        )
        assert result["feasible"] is False

    def test_startup_costs(self):
        result = self.bp.startup_costs([
            {"naziv": "Laptop", "iznos": 1500, "kategorija": "IT"},
            {"naziv": "Ured", "iznos": 3000, "kategorija": "Najam"},
        ])
        assert result["total"] == 4500
        assert result["total_s_pdv"] == 5625


# ═══════════════════════════════════════════════════
# DPO TRAINER TESTS
# ═══════════════════════════════════════════════════

class TestDPOTrainer:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from nyx_light.finetune.nightly_dpo import NightlyDPOTrainer
        self.dpo = NightlyDPOTrainer(
            data_dir=self.tmpdir,
            model_dir=os.path.join(self.tmpdir, "models"),
        )

    def test_record_pair(self):
        self.dpo.record_pair(
            prompt="Kontiraj nabavu materijala",
            chosen="D: 3000, K: 2200",
            rejected="D: 4000, K: 2200",
            client_id="K001",
            module="kontiranje",
        )
        pairs = self.dpo.collect_todays_pairs()
        assert len(pairs) == 1
        assert pairs[0].chosen == "D: 3000, K: 2200"

    def test_collect_unused(self):
        for i in range(15):
            self.dpo.record_pair(f"Prompt {i}", f"Good {i}", f"Bad {i}")
        pairs = self.dpo.collect_unused_pairs()
        assert len(pairs) == 15

    def test_export_dataset(self):
        self.dpo.record_pair("P1", "C1", "R1")
        self.dpo.record_pair("P2", "C2", "R2")
        pairs = self.dpo.collect_unused_pairs()
        path = self.dpo.export_dataset(pairs)
        assert os.path.exists(path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_stats(self):
        self.dpo.record_pair("P", "C", "R")
        stats = self.dpo.get_stats()
        assert stats["total_pairs"] == 1
        assert stats["unused_pairs"] == 1
        assert stats["ready_for_training"] is False  # < 10

    def test_list_lora_adapters(self):
        adapters = self.dpo.list_lora_adapters()
        assert isinstance(adapters, list)
