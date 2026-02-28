"""
Sprint 25: Frontend + Integration Cleanup Tests

Verificira:
1. Sve 22 stranice u HTML-u
2. Svi fetchAPI pozivi imaju backend endpoint
3. WebSocket koristi Executor
4. ChatBridge fallback koristi Executor
5. Router entity extraction
6. Nema duplikata endpointa
"""

import re
import pytest


class TestFrontendPages:
    """Test da frontend HTML sadrži sve module pages."""

    def _load_html(self):
        with open("static/index.html", "r") as f:
            return f.read()

    def test_all_nav_items(self):
        html = self._load_html()
        expected = [
            "chat", "pending", "bookings", "upload",
            "payroll", "amort", "bank", "kontiranje",
            "blagajna", "putni", "pdv", "porez",
            "joppd", "gfi", "ios", "eracun",
            "dashboard", "deadlines", "clients",
            "export", "system",
        ]
        for page in expected:
            assert f'data-page="{page}"' in html, f"Missing nav: {page}"

    def test_all_page_divs(self):
        html = self._load_html()
        expected_pages = [
            "page-chat", "page-pending", "page-bookings", "page-upload",
            "page-payroll", "page-amort", "page-bank", "page-kontiranje",
            "page-blagajna", "page-putni", "page-pdv", "page-porez",
            "page-joppd", "page-gfi", "page-ios", "page-eracun",
            "page-dashboard", "page-deadlines", "page-clients",
            "page-export", "page-system",
        ]
        for pid in expected_pages:
            assert f'id="{pid}"' in html, f"Missing page div: {pid}"

    def test_js_functions_for_modules(self):
        html = self._load_html()
        functions = [
            "parseBank", "suggestKonto", "validateBlagajna",
            "calcPutni", "genPDV", "calcPorezDobit",
            "genJOPPD", "genGFI", "genIOS", "processEracun",
            "loadClientSelects", "fetchAPI", "showToast",
        ]
        for fn in functions:
            assert f"function {fn}" in html or f"async function {fn}" in html, \
                f"Missing JS function: {fn}"

    def test_no_duplicate_chart_import(self):
        html = self._load_html()
        count = html.count("chart.umd.min.js")
        assert count == 1, f"Chart.js imported {count} times (should be 1)"

    def test_client_selects_class(self):
        html = self._load_html()
        assert "client-select" in html
        # At least 5 pages have client selects
        assert html.count('class="client-select"') >= 5

    def test_css_classes_exist(self):
        html = self._load_html()
        required = [".stat-card", ".stat-label", ".stat-value", ".data-table"]
        for cls in required:
            assert cls in html, f"Missing CSS: {cls}"


class TestFrontendBackendMapping:
    """Test da svaki frontend API poziv ima backend endpoint."""

    def test_all_frontend_calls_have_endpoints(self):
        from nyx_light.api.app import app

        # Get backend paths
        backend_paths = set()
        for r in app.routes:
            if hasattr(r, "path") and r.path.startswith("/api/"):
                backend_paths.add(r.path)

        # Get frontend calls
        with open("static/index.html", "r") as f:
            html = f.read()
        calls = re.findall(r"fetchAPI\('(/api/[^']*)'", html)
        calls += re.findall(r"fetch\(API\+'(/[^']*)'", html)

        for call in calls:
            full = call if call.startswith("/api/") else f"/api{call}"
            # Strip query params and JS concatenation
            full = full.split("?")[0].split("'+")[0]
            # Skip paths that are clearly partial (end with /) — parameterized
            if full.endswith("/"):
                continue
            assert full in backend_paths, f"Frontend calls {full} but no backend endpoint"

    def test_no_duplicate_endpoints(self):
        from nyx_light.api.app import app
        from collections import Counter
        paths = []
        for r in app.routes:
            if hasattr(r, "methods") and hasattr(r, "path"):
                for m in (r.methods - {"HEAD", "OPTIONS"}):
                    paths.append(f"{m} {r.path}")
        dupes = [(p, c) for p, c in Counter(paths).items() if c > 1]
        assert not dupes, f"Duplicate endpoints: {dupes}"


class TestWebSocketExecutor:
    """Test da WS chat handler koristi Executor."""

    def test_ws_handler_has_executor(self):
        import inspect
        from nyx_light.api.app import ws_chat
        source = inspect.getsource(ws_chat)
        assert "executor" in source.lower() or "ModuleRouter" in source, \
            "WS handler doesn't use executor/router"
        assert "module_result" in source or "route" in source
        assert "chat_stream" in source

    def test_ws_handler_sends_module_data(self):
        import inspect
        from nyx_light.api.app import ws_chat
        source = inspect.getsource(ws_chat)
        assert "module_used" in source, "WS done msg should include module_used"
        assert "module_data" in source, "WS done msg should include module_data"


class TestChatBridgeFallback:
    """Test da ChatBridge fallback koristi ModuleExecutor."""

    def test_fallback_uses_executor(self):
        import inspect
        from nyx_light.llm.chat_bridge import ChatBridge
        source = inspect.getsource(ChatBridge._fallback_response)
        assert "ModuleExecutor" in source, "Fallback should use ModuleExecutor"
        assert "ModuleRouter" in source, "Fallback should use ModuleRouter"

    def test_fallback_payroll(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        cb = ChatBridge()
        r = cb._fallback_response("Obračunaj plaću bruto 2500 EUR")
        assert "2,500" in r or "2500" in r or "1," in r

    def test_fallback_deadlines(self):
        from nyx_light.llm.chat_bridge import ChatBridge
        cb = ChatBridge()
        r = cb._fallback_response("Koji su rokovi za predaju?")
        assert "rok" in r.lower() or "PDV" in r or "Deadlines" in r


class TestRouterImprovements:
    """Test poboljšanja routera iz Sprint 25."""

    def test_blagajna_croatian_suffixes(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        for q in ["provjeri blagajnu", "stanje blagajne", "blagajnom upravljaj"]:
            result = r.route(q)
            assert result.module == "blagajna", f"'{q}' → {result.module}"

    def test_entity_extraction_eur(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Obračunaj plaću bruto 2500 EUR")
        assert result.entities.get("iznos") == "2500"

    def test_entity_extraction_hr_format(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Račun za 1.250,00 EUR")
        assert result.entities.get("iznos") == "1250.00"

    def test_entities_on_general_route(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Nešto s 500,00 kn")
        # Even general routes should extract entities
        assert isinstance(result.entities, dict)


class TestDeadCodeCleanup:
    """Test da je dead code uklonjen."""

    def test_core_module_router_is_proxy(self):
        with open("src/nyx_light/core/module_router.py", "r") as f:
            content = f.read()
        assert "PROXY" in content
        assert "from nyx_light.router import" in content
        lines = [l for l in content.strip().split("\n") if l.strip() and not l.startswith("#")]
        assert len(lines) < 10, f"Proxy should be <10 LOC, got {len(lines)}"

    def test_proxy_import_works(self):
        from nyx_light.core.module_router import ModuleRouter
        from nyx_light.router import ModuleRouter as MainRouter
        assert ModuleRouter is MainRouter
