"""Tests za MoE (Mixture-of-Experts) konfiguraciju i memory management."""

from nyx_light.llm.provider import NyxLightLLM, LLMConfig, MoEConfig


class TestMoEConfig:
    """Provjeri MoE konfiguraciju."""

    def test_default_moe_config(self):
        config = LLMConfig()
        assert config.moe.total_params_b == 235.0
        assert config.moe.active_params_b == 22.0
        assert config.moe.num_experts == 128
        assert config.moe.active_experts_per_token == 8

    def test_model_name(self):
        config = LLMConfig()
        assert "Qwen3-235B-A22B" in config.default_model
        assert "Qwen3-VL-8B" in config.vision_model

    def test_total_memory_256gb(self):
        config = LLMConfig()
        assert config.total_memory_gb == 256.0

    def test_wired_memory_83pct(self):
        config = LLMConfig()
        wired = config.total_memory_gb * config.wired_memory_pct
        assert wired >= 210  # ~212 GB


class TestMoEMemoryEstimation:
    """Provjeri memory budget kalkulaciju."""

    def test_memory_estimate_basic(self):
        llm = NyxLightLLM()
        mem = llm.estimate_memory_usage()

        assert mem["model_architecture"] == "MoE"
        assert mem["total_params_b"] == 235.0
        assert mem["active_params_b"] == 22.0
        assert mem["model_memory_gb"] == 124.0
        assert mem["total_available_gb"] == 256.0
        assert mem["headroom_gb"] > 0

    def test_memory_without_vision(self):
        llm = NyxLightLLM()
        mem = llm.estimate_memory_usage()

        assert mem["vision_loaded"] is False
        assert mem["vision_memory_gb"] == 0.0

    def test_memory_peak_under_256gb(self):
        """Peak memory MORA biti ispod 256 GB."""
        llm = NyxLightLLM()
        mem = llm.estimate_memory_usage()

        assert mem["total_estimated_gb"] < 256.0, (
            f"Peak memory {mem['total_estimated_gb']} GB premašuje 256 GB!"
        )

    def test_headroom_at_least_50gb(self):
        """Mora biti barem 50 GB slobodno za stabilnost."""
        llm = NyxLightLLM()
        mem = llm.estimate_memory_usage()

        assert mem["headroom_gb"] >= 50.0, (
            f"Headroom {mem['headroom_gb']} GB — premalo za stabilan rad!"
        )


class TestVisionOnDemand:
    """Provjeri on-demand loading Vision modela."""

    def test_vision_not_loaded_by_default(self):
        llm = NyxLightLLM()
        assert llm._vision_loaded is False

    def test_vision_unload_config(self):
        config = LLMConfig()
        assert config.vision_unload_after_s == 300  # 5 minuta

    def test_maybe_unload_vision_idle(self):
        """Vision model se unloada nakon isteka timeouta."""
        import time
        llm = NyxLightLLM()
        llm._vision_loaded = True
        llm._vision_last_used = time.time() - 400  # 400s ago > 300s threshold
        llm.maybe_unload_vision()
        assert llm._vision_loaded is False


class TestFallbackModel:
    """Provjeri fallback model za low-memory scenarije."""

    def test_fallback_model_exists(self):
        config = LLMConfig()
        assert "Qwen3-30B-A3B" in config.fallback_model


class TestMoEStats:
    """Provjeri da stats sadrže MoE informacije."""

    def test_stats_include_moe_info(self):
        llm = NyxLightLLM()
        stats = llm.get_stats()

        assert stats["architecture"] == "MoE (Mixture-of-Experts)"
        assert stats["total_params_b"] == 235.0
        assert stats["active_params_b"] == 22.0
        assert "8/128" in stats["active_experts"]
        assert "memory" in stats
        assert stats["memory"]["model_architecture"] == "MoE"
