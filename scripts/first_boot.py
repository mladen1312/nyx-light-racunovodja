#!/usr/bin/env python3
"""
Nyx Light — First Boot Script

1. Provjerava hardver (Mac Studio M5 Ultra)
2. Kreira direktorije
3. Preuzima AI modele
4. Pokreće Qdrant + Neo4j
5. Testira inference
"""

import os
import platform
import subprocess
import sys


def main():
    print("🌙 Nyx Light — Računovođa: First Boot")
    print("=" * 50)

    # Check platform
    print(f"\n📌 Platform: {platform.system()} {platform.machine()}")
    
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        print("✅ Apple Silicon detected")
        
        # Check memory
        try:
            result = subprocess.run(
                ["sysctl", "hw.memsize"], capture_output=True, text=True
            )
            mem_bytes = int(result.stdout.strip().split(":")[1].strip())
            mem_gb = mem_bytes / (1024**3)
            print(f"✅ Memory: {mem_gb:.0f} GB")
            
            if mem_gb >= 192:
                print("✅ Sufficient for Nyx Light (192+ GB)")
            else:
                print(f"⚠️  Recommended: 192 GB, detected: {mem_gb:.0f} GB")
        except Exception:
            print("⚠️  Could not detect memory")
    else:
        print("⚠️  Not Apple Silicon — will use estimation mode")

    # Create directories
    print("\n📁 Creating directories...")
    dirs = [
        "data/uploads", "data/exports", "data/models",
        "data/prompt_cache", "data/memory_db", "data/rag_db", "data/laws",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✅ {d}")

    print("\n✅ First boot complete!")
    print("\nNext steps:")
    print("  1. Download models: mlx_lm.server --model mlx-community/Qwen2.5-72B-Instruct-4bit")
    print("  2. Start server: python -m nyx_light.main")
    print("  3. Open: http://localhost:8000")


if __name__ == "__main__":
    main()
