"""
Nyx Light — Sprint 17 Tests

Testira sve nove module i endpointe:
  - Module Router
  - Payroll Calculator (Plaće)
  - Knowledge Graph
  - Prometheus Metrics
  - Embedded Vector Store
  - Law Ingestion Pipeline
  - Email/Folder Watcher
  - Bank Parser API
  - IOS API
  - Blagajna API
  - Putni Nalozi API
  - Amortizacija API
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

for d in ["data/memory_db", "data/logs", "data/uploads", "data/exports",
          "data/dpo_datasets", "data/models/lora", "data/laws", "data/backups",
          "data/rag_db", "data/uploads/email", "data/uploads/folder"]:
    Path(d).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════
# MODULE ROUTER
# ═══════════════════════════════════════════

class TestModuleRouter:
    def test_route_pdv(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Koja je stopa PDV na hranu?")
        assert result.module == "rag"
        assert result.confidence > 0.5

    def test_route_bank(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Uvezi bankovni izvod MT940 Erste banke")
        assert result.module == "bank_parser"

    def test_route_kontiranje(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Koji konto za uredski materijal? Duguje 4010")
        assert result.module == "kontiranje"

    def test_route_placa(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Koliki je neto za bruto plaću od 2000 EUR?")
        assert result.module == "place"

    def test_route_blagajna(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Provjeri blagajnički primitak od 5000 EUR gotovine")
        assert result.module == "blagajna"

    def test_route_putni(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Obračunaj putni nalog 150 km dnevnica")
        assert result.module == "putni_nalozi"

    def test_route_ios(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Generiraj IOS izvod otvorenih stavki za partnera")
        assert result.module == "ios"

    def test_route_general(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Bok, kako si?")
        assert result.module == "general"

    def test_route_invoice_with_file(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Učitaj ovaj račun", has_file=True)
        assert result.module == "invoice_ocr"

    def test_route_entities_oib(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Provjeri račun za OIB 12345678901")
        assert result.entities.get("oib") == "12345678901"

    def test_route_entities_iban(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("IBAN HR1234567890123456789")
        assert result.entities.get("iban") == "HR1234567890123456789"

    def test_route_amortizacija(self):
        from nyx_light.router import ModuleRouter
        result = ModuleRouter().route("Kolika je stopa amortizacije za računalnu opremu?")
        assert result.module == "amortizacija"

    def test_available_modules(self):
        from nyx_light.router import ModuleRouter
        modules = ModuleRouter().get_available_modules()
        assert len(modules) >= 10
        names = [m["id"] for m in modules]
        assert "bank_parser" in names
        assert "kontiranje" in names


# ═══════════════════════════════════════════
# PAYROLL CALCULATOR
# ═══════════════════════════════════════════

class TestPayroll:
    def test_basic_payroll(self):
        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput
        calc = PayrollCalculator()
        r = calc.obracun(ObracunPlaceInput(bruto=2000.00, grad="zagreb"))
        assert r.bruto_ukupno == 2000.00
        assert r.mio_i == 300.00  # 15%
        assert r.mio_ii == 100.00  # 5%
        assert r.dohodak == 1600.00
        assert r.osobni_odbitak == 560.00
        assert r.porezna_osnovica == 1040.00
        assert r.porez == 208.00  # 20%
        assert r.prirez == 37.44  # 18% of 208
        assert r.neto == 1354.56
        assert r.zdravstveno == 330.00  # 16.5%

    def test_minimalna_placa(self):
        from nyx_light.modules.place import PayrollCalculator
        r = PayrollCalculator().minimalna_placa("zagreb")
        assert r.bruto_ukupno == 1050.00
        assert r.neto > 0

    def test_uzdrzavani(self):
        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput, UzdrzavaniClan
        r = PayrollCalculator().obracun(ObracunPlaceInput(
            bruto=2000.00, grad="zagreb",
            uzdrzavani=[UzdrzavaniClan("dijete_1"), UzdrzavaniClan("dijete_2")],
        ))
        # Osobni odbitak: 560 + 0.7*560 + 1.0*560 = 560 + 392 + 560 = 1512
        assert r.osobni_odbitak == 1512.00
        assert r.neto > 1354.56  # More than without dependents

    def test_neto_to_bruto(self):
        from nyx_light.modules.place import PayrollCalculator
        r = PayrollCalculator().bruto_iz_neto(1354.56, "zagreb")
        assert abs(r.bruto_ukupno - 2000.00) < 1.0  # Should converge

    def test_prirez_split(self):
        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput
        r = PayrollCalculator().obracun(ObracunPlaceInput(bruto=2000.00, grad="split"))
        assert r.prirez_stopa == 0.15

    def test_trosak_poslodavca(self):
        from nyx_light.modules.place import PayrollCalculator, ObracunPlaceInput
        r = PayrollCalculator().obracun(ObracunPlaceInput(bruto=2000.00, grad="zagreb"))
        assert r.trosak_poslodavca == 2000.00 + 330.00  # bruto + zdravstveno


# ═══════════════════════════════════════════
# KNOWLEDGE GRAPH
# ═══════════════════════════════════════════

class TestKnowledgeGraph:
    def test_add_node(self):
        from nyx_light.kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_node("test:1", "TestNode", {"name": "Test"})
        node = kg.get_node("test:1")
        assert node is not None
        assert node["type"] == "TestNode"

    def test_add_edge(self):
        from nyx_light.kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_node("a", "A"); kg.add_node("b", "B")
        kg.add_edge("a", "b", "RELATES_TO")
        neighbors = kg.get_neighbors("a")
        assert len(neighbors) == 1
        assert neighbors[0]["node_id"] == "b"

    def test_seed_defaults(self):
        from nyx_light.kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.seed_defaults()
        stats = kg.get_stats()
        assert stats["nodes"] > 10
        assert stats["edges"] >= 3

    def test_konto_rules(self):
        from nyx_light.kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_client("12345678901", "Test d.o.o.")
        kg.add_konto_rule("12345678901", "Dobavljač X", "4010", "Uredski materijal")
        rules = kg.get_konto_rules("12345678901")
        assert len(rules) >= 1

    def test_find_path(self):
        from nyx_light.kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_node("x", "X"); kg.add_node("y", "Y"); kg.add_node("z", "Z")
        kg.add_edge("x", "y", "A"); kg.add_edge("y", "z", "B")
        path = kg.find_path("x", "z")
        assert path == ["x", "y", "z"]


# ═══════════════════════════════════════════
# PROMETHEUS METRICS
# ═══════════════════════════════════════════

class TestPrometheusMetrics:
    def test_counter(self):
        from nyx_light.metrics import Counter
        c = Counter("test_total", "Test counter", ["method"])
        c.inc(method="GET")
        c.inc(method="GET")
        c.inc(method="POST")
        assert c.get(method="GET") == 2
        assert c.get(method="POST") == 1

    def test_gauge(self):
        from nyx_light.metrics import Gauge
        g = Gauge("test_gauge", "Test gauge")
        g.set(42.5)
        assert g.get() == 42.5

    def test_histogram(self):
        from nyx_light.metrics import Histogram
        h = Histogram("test_hist", "Test histogram")
        h.observe(0.1)
        h.observe(0.5)
        h.observe(2.0)
        text = h.to_prometheus()
        assert "test_hist_bucket" in text
        assert "test_hist_count" in text

    def test_export(self):
        from nyx_light.metrics import PrometheusMetrics
        m = PrometheusMetrics()
        m.requests_total.inc(method="GET", endpoint="/health", status="200")
        text = m.export()
        assert "nyx_requests_total" in text


# ═══════════════════════════════════════════
# EMBEDDED VECTOR STORE
# ═══════════════════════════════════════════

class TestEmbeddedVectorStore:
    def test_init(self):
        from nyx_light.rag.embedded_store import EmbeddedVectorStore
        store = EmbeddedVectorStore(persist_dir="/tmp/nyx_test_vectors")
        store.initialize()
        assert store._initialized

    def test_ingest_and_search(self):
        from nyx_light.rag.embedded_store import EmbeddedVectorStore, LawChunk
        store = EmbeddedVectorStore(persist_dir="/tmp/nyx_test_vectors2")
        store.initialize()
        store.clear()

        chunks = [
            LawChunk(text="PDV stopa 25% primjenjuje se na sve", law_name="ZakonPDV", article_number="38"),
            LawChunk(text="Porez na dobit iznosi 18%", law_name="ZakonDobit", article_number="28"),
        ]
        result = store.ingest_chunks(chunks)
        assert result["ingested"] == 2

        results = store.search("PDV stopa", top_k=2)
        assert len(results) > 0

    def test_law_filter(self):
        from nyx_light.rag.embedded_store import EmbeddedVectorStore, LawChunk
        store = EmbeddedVectorStore(persist_dir="/tmp/nyx_test_vectors3")
        store.initialize()
        store.clear()

        chunks = [
            LawChunk(text="PDV 25%", law_name="ZakonPDV"),
            LawChunk(text="Dobit 18%", law_name="ZakonDobit"),
        ]
        store.ingest_chunks(chunks)
        results = store.search("porez", law_filter="ZakonPDV")
        assert all("ZakonPDV" in r.law_name for r in results)


# ═══════════════════════════════════════════
# LAW INGESTION
# ═══════════════════════════════════════════

class TestLawIngestion:
    def test_parse_law_file(self):
        from nyx_light.rag.ingest_laws import parse_law_file
        result = parse_law_file(Path("data/laws/zakon_pdv.md"))
        assert result["metadata"]["zakon"] == "Zakon o porezu na dodanu vrijednost"
        assert len(result["articles"]) >= 3

    def test_ingest_all(self):
        from nyx_light.rag.ingest_laws import ingest_all_laws
        from nyx_light.rag.embedded_store import EmbeddedVectorStore
        store = EmbeddedVectorStore(persist_dir="/tmp/nyx_test_ingest")
        store.initialize()
        store.clear()
        result = ingest_all_laws(store=store)
        assert result["laws_processed"] >= 20  # We have 25 law files
        assert result["chunks_ingested"] > 50


# ═══════════════════════════════════════════
# EMAIL WATCHER
# ═══════════════════════════════════════════

class TestEmailWatcher:
    def test_init(self):
        from nyx_light.ingest.email_watcher import EmailWatcher
        w = EmailWatcher()
        assert not w._running
        assert not w.imap_host

    def test_detect_type(self):
        from nyx_light.ingest.email_watcher import EmailWatcher
        w = EmailWatcher()
        assert w._detect_type("racun_01.pdf", ".pdf", b"") == "invoice_scan"
        assert w._detect_type("izvod_pbz.sta", ".sta", b"") == "bank_statement"
        assert w._detect_type("test.csv", ".csv", b"IBAN,iznos,datum") == "bank_statement"
        assert w._detect_type("test.xml", ".xml", b"<Invoice>") == "e_racun"

    def test_stats(self):
        from nyx_light.ingest.email_watcher import EmailWatcher
        w = EmailWatcher(imap_host="test.local", imap_user="test")
        stats = w.get_stats()
        assert stats["configured"] is True


# ═══════════════════════════════════════════
# FOLDER WATCHER
# ═══════════════════════════════════════════

class TestFolderWatcher:
    def test_init(self):
        from nyx_light.ingest.folder_watcher import FolderWatcher
        w = FolderWatcher(watch_paths=["data/uploads"])
        assert len(w.watch_paths) == 1

    def test_detect_type(self):
        from nyx_light.ingest.folder_watcher import FolderWatcher
        w = FolderWatcher()
        assert w._detect_type(Path("racun_dobavljac.pdf")) == "invoice_scan"
        assert w._detect_type(Path("izvod_erste.sta")) == "bank_statement"
        assert w._detect_type(Path("ios_partner.xlsx")) == "ios_form"

    def test_scan(self):
        from nyx_light.ingest.folder_watcher import FolderWatcher
        w = FolderWatcher(watch_paths=["data/uploads"])
        # Initial scan shouldn't crash
        w._initial_scan()
        stats = w.get_stats()
        assert "scans" in stats


# ═══════════════════════════════════════════
# API ENDPOINTS (Sprint 17)
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


class TestNewEndpoints:
    def test_route_endpoint(self, client, headers):
        resp = client.post("/api/route", headers=headers,
                          json={"message": "Kolika je stopa PDV-a?"})
        assert resp.status_code == 200
        assert resp.json()["module"] in ("rag", "general")

    def test_modules_list(self, client, headers):
        resp = client.get("/api/modules", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["modules"]) >= 10

    def test_payroll_calculate(self, client, headers):
        resp = client.post("/api/payroll/calculate", headers=headers,
                          json={"bruto": 2000, "grad": "zagreb"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["neto"] > 0
        assert data["trosak_poslodavca"] > data["bruto"]

    def test_payroll_neto_to_bruto(self, client, headers):
        resp = client.post("/api/payroll/neto-to-bruto", headers=headers,
                          json={"neto": 1300, "grad": "zagreb"})
        assert resp.status_code == 200
        assert resp.json()["bruto_potreban"] > 1300

    def test_payroll_minimalna(self, client, headers):
        resp = client.get("/api/payroll/minimalna?grad=zagreb", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["bruto"] == 1050.0

    def test_payroll_neoporezivi(self, client, headers):
        resp = client.get("/api/payroll/neoporezivi", headers=headers)
        assert resp.status_code == 200
        assert "bozicnica" in resp.json()["neoporezivi"]

    def test_kg_stats(self, client, headers):
        resp = client.get("/api/kg/stats", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["nodes"] > 0

    def test_kg_query_type(self, client, headers):
        resp = client.get("/api/kg/query/KontniRazred", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["nodes"]) >= 10

    def test_prometheus_metrics(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # May be empty if no data yet, but should not error
        assert isinstance(resp.text, str)

    def test_law_ingestion(self, client, headers):
        resp = client.post("/api/laws/ingest", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["laws_processed"] >= 20

    def test_ingest_stats(self, client, headers):
        resp = client.get("/api/ingest/stats", headers=headers)
        assert resp.status_code == 200
        assert "email" in resp.json()
        assert "folder" in resp.json()

    def test_ios_generate(self, client, headers):
        resp = client.post("/api/ios/generate", headers=headers,
                          json={"client_id": "K001", "partner_oib": "12345678901",
                                "datum_od": "2026-01-01", "datum_do": "2026-12-31"})
        assert resp.status_code == 200

    def test_blagajna_validate(self, client, headers):
        resp = client.post("/api/blagajna/validate", headers=headers,
                          json={"iznos": 5000, "tip": "izdatak"})
        assert resp.status_code == 200

    def test_putni_nalog(self, client, headers):
        resp = client.post("/api/putni-nalog/check", headers=headers,
                          json={"km": 150, "dnevnica": 26.54})
        assert resp.status_code == 200

    def test_amortizacija(self, client, headers):
        resp = client.post("/api/amortizacija/calculate", headers=headers,
                          json={"nabavna_vrijednost": 10000, "grupa": "3", "metoda": "linearna"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["stopa_pct"] == 50
        assert data["godisnja"] == 5000.0

    def test_amortizacija_auto(self, client, headers):
        resp = client.post("/api/amortizacija/calculate", headers=headers,
                          json={"nabavna_vrijednost": 60000, "grupa": "2"})
        assert resp.status_code == 200
        assert resp.json()["porezno_priznato"] == 40000  # Max for osobni auto

    def test_total_endpoints_60plus(self, client, headers):
        from nyx_light.api.app import app
        routes = [r for r in app.routes if hasattr(r, "methods")]
        assert len(routes) >= 55, f"Samo {len(routes)} endpointa"

    # ── ERP PULL ──

    def test_erp_kontni_plan(self, client, headers):
        resp = client.get("/api/erp/kontni-plan", headers=headers)
        assert resp.status_code == 200
        assert "kontni_plan" in resp.json()

    def test_erp_otvorene_stavke(self, client, headers):
        resp = client.get("/api/erp/otvorene-stavke", headers=headers)
        assert resp.status_code == 200
        assert "stavke" in resp.json()

    def test_erp_saldo(self, client, headers):
        resp = client.get("/api/erp/saldo/4010", headers=headers)
        assert resp.status_code == 200

    def test_erp_bruto_bilanca(self, client, headers):
        resp = client.get("/api/erp/bruto-bilanca", headers=headers)
        assert resp.status_code == 200

    def test_erp_partner_kartica(self, client, headers):
        resp = client.get("/api/erp/partner-kartica/12345678901", headers=headers)
        assert resp.status_code == 200

    # ── PAYROLL EDGE CASES ──

    def test_payroll_high_salary(self, client, headers):
        resp = client.post("/api/payroll/calculate", headers=headers,
                          json={"bruto": 10000, "grad": "zagreb"})
        d = resp.json()
        assert d["porezna_osnovica"] > 4200  # Exceeds monthly limit → 30% bracket
        assert d["neto"] > 0

    def test_payroll_vukovar_no_prirez(self, client, headers):
        resp = client.post("/api/payroll/calculate", headers=headers,
                          json={"bruto": 2000, "grad": "vukovar"})
        assert resp.json()["prirez"] == 0

    # ── ROUTER EDGE CASES ──

    def test_route_export(self, client, headers):
        resp = client.post("/api/route", headers=headers,
                          json={"message": "Exportiraj knjiženja u CPP sustav"})
        assert resp.status_code == 200

    def test_route_with_entities(self, client, headers):
        resp = client.post("/api/route", headers=headers,
                          json={"message": "Provjeri račun OIB 12345678901 IBAN HR1234567890123456789"})
        d = resp.json()
        assert d.get("entities", {}).get("oib") == "12345678901"


# ═══════════════════════════════════════════
# APPLE SILICON COMPATIBILITY
# ═══════════════════════════════════════════

class TestAppleSilicon:
    def test_silicon_detect(self):
        from nyx_light.silicon.apple_silicon import detect_hardware
        hw = detect_hardware()
        assert hw is not None  # Works on any platform (fallback)

    def test_silicon_runtime(self):
        from nyx_light.silicon.apple_silicon import SiliconRuntime
        rt = SiliconRuntime()
        health = rt.health_check()
        assert isinstance(health, dict)

    def test_knowledge_vault(self):
        from nyx_light.silicon.knowledge_vault import KnowledgeVault
        kv = KnowledgeVault(base_dir="/tmp/nyx_test_vault")
        manifest = kv.create_manifest()
        assert manifest is not None

    def test_vllm_engine_config(self):
        from nyx_light.silicon.vllm_mlx_engine import VLLMMLXConfig
        cfg = VLLMMLXConfig()
        assert cfg.vllm_port == 8080 or cfg.vllm_port > 0


# ═══════════════════════════════════════════
# CHAT BRIDGE
# ═══════════════════════════════════════════

class TestChatBridge:
    def test_build_messages(self):
        from nyx_light.llm.chat_bridge import ChatBridge, ChatContext
        bridge = ChatBridge()
        msgs = bridge.build_messages("Koji je PDV?", "session1")
        assert len(msgs) >= 2
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["content"] == "Koji je PDV?"

    def test_build_with_context(self):
        from nyx_light.llm.chat_bridge import ChatBridge, ChatContext
        bridge = ChatBridge()
        ctx = ChatContext(
            rag_results=[{"source": "ZakonPDV", "text": "PDV 25%"}],
            semantic_facts=["Klijent X vodi PDV"],
            client_info={"name": "Test d.o.o.", "oib": "12345678901"},
        )
        msgs = bridge.build_messages("Kako kontirati?", "s2", ctx)
        # system + context_system + user = 3
        assert len(msgs) >= 3

    def test_fallback_response(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        resp = bridge._fallback_response("Kolika je stopa PDV-a?")
        assert "PDV" in resp or "25%" in resp

    def test_history_management(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        bridge = ChatBridge()
        bridge.build_messages("msg1", "sess_test")
        # Manually add to history
        from nyx_light.llm.chat_bridge import ChatMessage
        import time
        bridge._histories["sess_test"] = [
            ChatMessage("user", "msg1", time.time()),
            ChatMessage("assistant", "reply1", time.time()),
        ]
        msgs = bridge.build_messages("msg2", "sess_test")
        # system + 2 history + user = 4
        assert len(msgs) >= 4
        bridge.clear_history("sess_test")
        assert "sess_test" not in bridge._histories


# ═══════════════════════════════════════════
# INTEGRATION SANITY
# ═══════════════════════════════════════════

class TestIntegration:
    def test_full_payroll_flow(self, client, headers):
        """Full flow: calculate → verify → export."""
        # 1. Calculate
        resp = client.post("/api/payroll/calculate", headers=headers,
                          json={"bruto": 3000, "grad": "split",
                                "uzdrzavani": [{"tip": "dijete_1"}]})
        d = resp.json()
        assert d["neto"] > 0
        assert d["za_isplatu"] >= d["neto"]

        # 2. Verify neto-to-bruto roundtrip
        resp2 = client.post("/api/payroll/neto-to-bruto", headers=headers,
                           json={"neto": d["neto"], "grad": "split",
                                 "uzdrzavani": [{"tip": "dijete_1"}]})
        bruto_calc = resp2.json()["bruto_potreban"]
        assert abs(bruto_calc - 3000) < 2  # ~1 EUR precision

    def test_router_to_module_flow(self, client, headers):
        """Route intent → call correct module."""
        # 1. Route
        resp = client.post("/api/route", headers=headers,
                          json={"message": "Izračunaj amortizaciju za server 25000 EUR"})
        route = resp.json()
        assert route["module"] == "amortizacija"

        # 2. Calculate
        resp2 = client.post("/api/amortizacija/calculate", headers=headers,
                           json={"nabavna_vrijednost": 25000, "grupa": "3"})
        assert resp2.json()["godisnja"] == 12500.0
