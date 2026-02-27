"""
Nyx Light — Silicon Package

Apple Silicon optimization layer.
"""

from .apple_silicon import (
    ChipGeneration,
    ChipVariant,
    DetectedHardware,
    PressureLevel,
    ThermalState,
    MemoryRegionType,
    detect_hardware,
    SiliconRuntime,
    UMAController,
    AdaptiveBatchController,
)

from .knowledge_vault import (
    KnowledgeVault,
    IntegrityManifest,
    LoRACompatibility,
    SwapPhase,
)

from .vllm_mlx_engine import (
    VLLMMLXEngine,
    VLLMMLXConfig,
    InferenceBackend,
    PromptCache,
)

__all__ = [
    "ChipGeneration", "ChipVariant", "DetectedHardware",
    "PressureLevel", "ThermalState", "MemoryRegionType",
    "detect_hardware", "SiliconRuntime", "UMAController", "AdaptiveBatchController",
    "KnowledgeVault", "IntegrityManifest", "LoRACompatibility", "SwapPhase",
    "VLLMMLXEngine", "VLLMMLXConfig", "InferenceBackend", "PromptCache",
]
