"""
Sprint 24 — Full Integration Tests

Verificira:
  1. ModuleExecutor ima handler za svaki modul
  2. Router pokriva sve module
  3. API ima endpointe za sve module
  4. Chat flow integrira Router → Executor → LLM
  5. NyxLightApp spojen na API
"""

import pytest


class TestModuleExecutor:
    def test_executor_imports(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        assert ex is not None

    def test_executor_has_all_handlers(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        assert len(ex.get_available_modules()) >= 40

    def test_executor_all_handlers_callable(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        for mod in ex.get_available_modules():
            result = ex.execute(mod)
            assert result is not None
            assert result.module == mod
            assert result.summary

    def test_executor_no_errors_on_info(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        errors = []
        for mod in ex.get_available_modules():
            result = ex.execute(mod)
            if not result.success and "datotek" not in result.summary.lower():
                errors.append(f"{mod}: {result.errors}")
        assert not errors, f"Moduli s greškama: {errors}"

    def test_executor_stats_tracking(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        ex.execute("kontiranje")
        ex.execute("blagajna")
        ex.execute("kontiranje")
        stats = ex.get_stats()
        assert stats["total_executions"] == 3
        assert stats["by_module"]["kontiranje"] == 2

    def test_executor_kontiranje_with_data(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        result = ex.execute("kontiranje", sub_intent="suggest",
                            data={"document_type": "ulazni_racun", "opis": "uredski materijal"})
        assert result.success
        assert result.llm_context

    def test_executor_place_with_bruto(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        result = ex.execute("place", data={"bruto": 2000})
        assert result.success
        assert result.data

    def test_executor_porez_dobit_with_data(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        result = ex.execute("porez_dobit", data={"prihod": 500000, "rashod": 400000})
        assert result.success

    def test_executor_deadlines(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        result = ex.execute("deadlines", data={"days": 30})
        assert result.success

    def test_executor_unknown_module(self):
        from nyx_light.api.module_executor import ModuleExecutor
        ex = ModuleExecutor()
        result = ex.execute("nepostojeci_modul")
        assert not result.success


class TestRouterCoverage:
    def test_router_has_all_modules(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        assert len(r.get_available_modules()) >= 40

    def test_router_critical_patterns(self):
        from nyx_light.router import INTENT_PATTERNS
        critical = ["bank_parser", "invoice_ocr", "kontiranje", "blagajna",
                     "putni_nalozi", "ios", "rag", "place", "porez_dobit",
                     "pdv_prijava", "kompenzacije", "e_racun", "peppol",
                     "fiskalizacija2", "intrastat", "gfi_xml"]
        for mod in critical:
            assert mod in INTENT_PATTERNS, f"Nema pattern: {mod}"

    def test_router_bank_statement(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Parsiraj MT940 izvod od Erste banke")
        assert result.module == "bank_parser"
        assert result.confidence > 0.6

    def test_router_kontiranje(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Kontira ovaj račun na konto 4010 duguje")
        assert result.module == "kontiranje"
        assert result.confidence > 0.6

    def test_router_general_fallback(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("Dobar dan, kako si?")
        assert result.module == "general"

    def test_router_entity_extraction(self):
        from nyx_light.router import ModuleRouter
        r = ModuleRouter()
        result = r.route("OIB 12345678901 IBAN HR1234567890123456789")
        assert "oib" in result.entities or "iban" in result.entities


class TestAPICoverage:
    def test_api_endpoint_count(self):
        from nyx_light.api.app import app
        routes = [r for r in app.routes if hasattr(r, 'methods')]
        assert len(routes) >= 100, f"Samo {len(routes)} endpointa"

    def test_api_critical_endpoints(self):
        from nyx_light.api.app import app
        paths = {r.path for r in app.routes if hasattr(r, 'path')}
        critical = [
            "/api/chat", "/api/route", "/api/module/execute", "/api/module/list",
            "/api/bank/parse", "/api/kontiranje/suggest", "/api/blagajna/validate",
            "/api/putni-nalog/check", "/api/ios/generate", "/api/payroll/calculate",
            "/api/pdv-prijava/generate", "/api/porez-dobit/calculate",
            "/api/e-racun/generate", "/api/gfi/bilanca", "/api/kompenzacije/find",
            "/api/joppd/generate-xml", "/api/export", "/api/upload",
            "/api/osnovna-sredstva/depreciation", "/api/fakturiranje/create",
            "/api/peppol/validate", "/api/fiskalizacija/fiscalize",
            "/api/intrastat/check", "/api/bolovanje/calculate",
            "/api/drugi-dohodak/calculate", "/api/porez-dohodak/calculate",
            "/api/ledger/dnevnik", "/api/likvidacija/start",
            "/api/accruals/checklist", "/api/novcani-tokovi/report",
            "/api/kpi/calculate", "/api/management-accounting/report",
            "/api/business-plan/generate", "/api/kadrovska/employees",
            "/api/communication/send", "/api/deadlines/upcoming",
            "/api/eracuni/parse", "/api/universal-parser/parse",
            "/api/outgoing-invoice/validate", "/api/vision/process",
            "/api/gfi/prep", "/api/network/status", "/api/scalability/metrics",
            "/api/audit/trail",
            "/api/nyx/process-invoice", "/api/nyx/process-bank",
            "/api/nyx/export-erp", "/api/nyx/status",
        ]
        missing = [ep for ep in critical if ep not in paths]
        assert not missing, f"Nedostaju: {missing}"

    def test_api_appstate_has_executor(self):
        from nyx_light.api.app import AppState
        state = AppState()
        assert hasattr(state, "nyx_app")
        assert hasattr(state, "executor")


class TestIntegrationFlow:
    def test_router_to_executor_blagajna(self):
        from nyx_light.router import ModuleRouter
        from nyx_light.api.module_executor import ModuleExecutor
        router = ModuleRouter()
        executor = ModuleExecutor()
        route = router.route("Provjeri blagajnički nalog za 5000 EUR gotovine")
        assert route.module == "blagajna"
        result = executor.execute(route.module, route.sub_intent, route.entities)
        assert result.module == "blagajna"
        assert result.llm_context

    def test_router_to_executor_kontiranje(self):
        from nyx_light.router import ModuleRouter
        from nyx_light.api.module_executor import ModuleExecutor
        router = ModuleRouter()
        executor = ModuleExecutor()
        route = router.route("Kontira nabavu uredskog materijala konto 4010")
        result = executor.execute(route.module, route.sub_intent, route.entities)
        assert result.success
        assert result.llm_context

    def test_router_to_executor_rag(self):
        from nyx_light.router import ModuleRouter
        from nyx_light.api.module_executor import ModuleExecutor
        router = ModuleRouter()
        executor = ModuleExecutor()
        route = router.route("Prema Zakonu o PDV-u, koja je stopa za hranu?")
        assert route.module == "rag"
        result = executor.execute(route.module, route.sub_intent, route.entities)
        assert result.success


class TestNyxLightApp:
    def test_nyx_app_imports(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        assert app is not None

    def test_nyx_app_critical_methods(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        methods = dir(app)
        critical = ["process_invoice", "process_bank_statement", "process_petty_cash",
                     "process_travel_expense", "prepare_pdv_prijava",
                     "export_to_erp", "approve", "reject", "correct",
                     "get_system_status", "get_pending"]
        missing = [m for m in critical if m not in methods]
        assert not missing, f"Nedostaju: {missing}"

    def test_nyx_app_system_status(self):
        from nyx_light.app import NyxLightApp
        app = NyxLightApp()
        status = app.get_system_status()
        assert isinstance(status, dict)
