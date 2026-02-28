"""
Tests: Deployment Infrastructure (Sprint 22)
═════════════════════════════════════════════
Memory budget, LLM stacks, hot-reload, remote config, services.
"""

import pytest
import time
import tempfile
from pathlib import Path
from decimal import Decimal


class TestMemoryBudget:
    """Testovi za memory budget calculator."""

    def test_premium_256gb_feasible(self):
        from nyx_light.deployment import calculate_budget
        budget = calculate_budget("premium_256gb", total_ram=256)
        assert budget.is_feasible
        assert budget.total_gb == 256
        assert budget.free_gb >= 10  # Min buffer

    def test_balanced_256gb_feasible(self):
        from nyx_light.deployment import calculate_budget
        budget = calculate_budget("balanced_256gb", total_ram=256)
        assert budget.is_feasible
        assert budget.free_gb >= 20

    def test_speed_256gb_most_headroom(self):
        from nyx_light.deployment import calculate_budget
        speed = calculate_budget("speed_256gb", total_ram=256)
        premium = calculate_budget("premium_256gb", total_ram=256)
        assert speed.free_gb > premium.free_gb

    def test_all_stacks_have_models(self):
        from nyx_light.deployment import STACK_CONFIGS
        for name, stack in STACK_CONFIGS.items():
            assert stack["reasoning"] is not None, f"{name} missing reasoning"
            assert stack["vision"] is not None, f"{name} missing vision"
            assert stack["embedding"] is not None, f"{name} missing embedding"

    def test_budget_summary(self):
        from nyx_light.deployment import calculate_budget
        budget = calculate_budget("premium_256gb")
        summary = budget.summary()
        assert "total_gb" in summary
        assert "reasoning" in summary
        assert "vision" in summary
        assert "embedding" in summary
        assert "utilization_pct" in summary
        assert summary["feasible"] == True

    def test_model_specs(self):
        from nyx_light.deployment import QWEN3_235B_A22B, QWEN25_VL_72B
        assert QWEN3_235B_A22B.params_billions == 235
        assert QWEN3_235B_A22B.role == "reasoning"
        assert QWEN25_VL_72B.role == "vision"
        assert QWEN25_VL_72B.ram_gb > 0

    def test_kv_cache_scales_with_users(self):
        from nyx_light.deployment import _kv_cache_estimate
        kv_5 = _kv_cache_estimate(131072, 32768, concurrent_users=5)
        kv_15 = _kv_cache_estimate(131072, 32768, concurrent_users=15)
        kv_25 = _kv_cache_estimate(131072, 32768, concurrent_users=25)
        assert kv_5 < kv_15 < kv_25


class TestRecommendStack:
    """Testovi za stack recommendation."""

    def test_recommend_quality(self):
        from nyx_light.deployment import recommend_stack
        r = recommend_stack(256, "quality")
        assert r["recommended_stack"] == "premium_256gb"
        assert "Qwen3-235B" in r["models"]["reasoning"]

    def test_recommend_speed(self):
        from nyx_light.deployment import recommend_stack
        r = recommend_stack(256, "speed")
        assert r["recommended_stack"] == "speed_256gb"
        assert r["stack_info"]["concurrent_users"] >= 20

    def test_recommend_balanced(self):
        from nyx_light.deployment import recommend_stack
        r = recommend_stack(256, "balanced")
        assert "memory_budget" in r
        assert r["memory_budget"]["feasible"] == True

    def test_recommend_has_performance(self):
        from nyx_light.deployment import recommend_stack
        r = recommend_stack(256, "quality")
        perf = r["performance"]
        assert perf["reasoning_tok_s"] > 0
        assert perf["vision_tok_s"] > 0
        assert perf["reasoning_ctx"] >= 32768


class TestHotReloadWatcher:
    """Testovi za hot-reload file watcher."""

    def test_watcher_detects_new_file(self):
        from nyx_light.deployment import HotReloadWatcher
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = HotReloadWatcher(
                watch_dirs=[tmpdir], check_interval=0.1)
            changes = []
            watcher.on_change(lambda c: changes.append(c))
            watcher.start()

            # Kreiraj novu datoteku
            time.sleep(0.2)
            (Path(tmpdir) / "test_new.py").write_text("print('hello')")
            time.sleep(0.5)

            watcher.stop()
            assert any(c.action == "created" for c in changes)

    def test_watcher_detects_modification(self):
        from nyx_light.deployment import HotReloadWatcher
        with tempfile.TemporaryDirectory() as tmpdir:
            # Kreiraj datoteku prije watchera
            test_file = Path(tmpdir) / "existing.py"
            test_file.write_text("x = 1")
            time.sleep(0.1)

            watcher = HotReloadWatcher(
                watch_dirs=[tmpdir], check_interval=0.1)
            changes = []
            watcher.on_change(lambda c: changes.append(c))
            watcher.start()
            time.sleep(0.3)

            # Modificiraj datoteku
            test_file.write_text("x = 2  # changed")
            time.sleep(0.5)

            watcher.stop()
            assert any(c.action == "modified" for c in changes)

    def test_watcher_ignores_pycache(self):
        from nyx_light.deployment import HotReloadWatcher
        with tempfile.TemporaryDirectory() as tmpdir:
            watcher = HotReloadWatcher(watch_dirs=[tmpdir])
            # __pycache__ should be ignored
            pycache = Path(tmpdir) / "__pycache__"
            pycache.mkdir()
            assert watcher._should_ignore(str(pycache / "test.pyc"))

    def test_watcher_get_changes(self):
        from nyx_light.deployment import HotReloadWatcher
        watcher = HotReloadWatcher(watch_dirs=["/nonexistent"])
        changes = watcher.get_changes()
        assert isinstance(changes, list)


class TestModuleReloader:
    """Testovi za module reloader."""

    def test_path_to_module(self):
        from nyx_light.deployment import ModuleReloader
        r = ModuleReloader()
        assert r._path_to_module("src/nyx_light/modules/ledger/__init__.py") == \
            "nyx_light.modules.ledger"
        assert r._path_to_module("src/nyx_light/core/config.py") == \
            "nyx_light.core.config"

    def test_reload_loaded_module(self):
        from nyx_light.deployment import ModuleReloader
        r = ModuleReloader()
        # nyx_light.deployment je loaded — trebao bi reloadati
        result = r.reload_module("src/nyx_light/deployment/__init__.py")
        assert result["status"] == "reloaded"

    def test_reload_nonexistent_module(self):
        from nyx_light.deployment import ModuleReloader
        r = ModuleReloader()
        result = r.reload_module("src/nyx_light/nonexistent_module/__init__.py")
        assert result["status"] == "skip"

    def test_reloader_stats(self):
        from nyx_light.deployment import ModuleReloader
        r = ModuleReloader()
        stats = r.get_stats()
        assert "total_reloads" in stats


class TestRemoteDevConfig:
    """Testovi za remote development konfiguraciju."""

    def test_default_config(self):
        from nyx_light.deployment import RemoteDevConfig
        config = RemoteDevConfig()
        assert config.api_port == 8420
        assert config.ssh_key_auth_only == True
        assert config.tailscale_enabled == True

    def test_ssh_config_generation(self):
        from nyx_light.deployment import RemoteDevConfig
        config = RemoteDevConfig()
        ssh = config.generate_ssh_config()
        assert "nyx-studio" in ssh
        assert "IdentityFile" in ssh
        assert str(config.api_port) in ssh

    def test_vscode_settings(self):
        from nyx_light.deployment import RemoteDevConfig
        config = RemoteDevConfig()
        settings = config.generate_vscode_settings()
        assert "ms-python.python" in settings["remote.SSH.defaultExtensions"]
        assert settings["python.testing.pytestEnabled"] == True


class TestServiceManager:
    """Testovi za macOS launchd service generator."""

    def test_api_plist_valid_xml(self):
        from nyx_light.deployment import ServiceManager, RemoteDevConfig
        import xml.etree.ElementTree as ET
        config = RemoteDevConfig()
        plist = ServiceManager.generate_api_plist(config)
        # Should be valid XML
        root = ET.fromstring(plist)
        assert root.tag == "plist"

    def test_api_plist_has_uvicorn(self):
        from nyx_light.deployment import ServiceManager, RemoteDevConfig
        config = RemoteDevConfig()
        plist = ServiceManager.generate_api_plist(config)
        assert "uvicorn" in plist
        assert "--reload" in plist  # Hot-reload enabled
        assert str(config.api_port) in plist

    def test_mlx_plist_valid(self):
        from nyx_light.deployment import ServiceManager, RemoteDevConfig
        import xml.etree.ElementTree as ET
        config = RemoteDevConfig()
        plist = ServiceManager.generate_mlx_plist(config)
        root = ET.fromstring(plist)
        assert "mlx" in plist

    def test_watcher_plist_valid(self):
        from nyx_light.deployment import ServiceManager, RemoteDevConfig
        import xml.etree.ElementTree as ET
        config = RemoteDevConfig()
        plist = ServiceManager.generate_watcher_plist(config)
        root = ET.fromstring(plist)
        assert "watcher" in plist


class TestDeploymentGenerator:
    """Testovi za deployment script generator."""

    def test_setup_script(self):
        from nyx_light.deployment import DeploymentGenerator, RemoteDevConfig
        config = RemoteDevConfig()
        script = DeploymentGenerator.generate_setup_script(config)
        assert "#!/bin/bash" in script
        assert "brew install" in script
        assert "pip install mlx" in script
        assert "pytest" in script

    def test_deploy_script(self):
        from nyx_light.deployment import DeploymentGenerator, RemoteDevConfig
        config = RemoteDevConfig()
        script = DeploymentGenerator.generate_deploy_script(config)
        assert "git fetch" in script
        assert "pytest" in script

    def test_live_edit_script(self):
        from nyx_light.deployment import DeploymentGenerator, RemoteDevConfig
        config = RemoteDevConfig()
        script = DeploymentGenerator.generate_live_edit_script(config)
        assert "nyx-test" in script
        assert "Hot-reload" in script


class TestHealthMonitor:
    """Testovi za health monitoring."""

    def test_health_check_structure(self):
        from nyx_light.deployment import HealthMonitor
        monitor = HealthMonitor()
        result = monitor.check_all()
        assert "overall" in result
        assert "services" in result
        assert "timestamp" in result

    def test_memory_check(self):
        from nyx_light.deployment import HealthMonitor
        monitor = HealthMonitor()
        mem = monitor._check_memory()
        assert "status" in mem


class TestGetStats:
    """Testovi za stats function."""

    def test_stats(self):
        from nyx_light.deployment import get_stats
        stats = get_stats()
        assert "available_stacks" in stats
        assert len(stats["available_stacks"]) >= 3
        assert "reasoning" in stats["models"]
        assert "vision" in stats["models"]
