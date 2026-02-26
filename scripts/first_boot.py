#!/usr/bin/env python3
"""
Nyx Light — First Boot Check

Pokrenite nakon instalacije za provjeru:
  python -m scripts.first_boot
"""

import importlib, os, platform, shutil, subprocess, sys
from pathlib import Path
import urllib.request

def p(icon, msg): print(f"  {icon} {msg}")

def main():
    print("═" * 60)
    print("  🌙 Nyx Light — Računovođa: First Boot Check")
    print("═" * 60)
    
    # ── Hardver ──
    print("\n🔧 HARDVER")
    print(f"  OS: {platform.platform()}")
    print(f"  Python: {platform.python_version()}")
    
    if platform.system() == "Darwin":
        try:
            chip = subprocess.check_output(["sysctl","-n","machdep.cpu.brand_string"], text=True).strip()
            mem = int(subprocess.check_output(["sysctl","-n","hw.memsize"], text=True).strip()) // (1024**3)
            p("✅" if "M" in chip else "⚠️", f"Čip: {chip}")
            p("✅" if mem >= 192 else "⚠️", f"RAM: {mem} GB {'(ok)' if mem >= 192 else '(preporučeno 192 GB)'}")
        except: p("⚠️", "Ne mogu detektirati hardver")
        try:
            wired = subprocess.check_output(["sysctl","-n","iogpu.wired_limit_mb"], text=True).strip()
            p("✅", f"Wired limit: {int(wired)//1024} GB")
        except: p("⚠️", "Wired limit nije postavljen → sudo sysctl iogpu.wired_limit_mb=163840")
    
    total, _, free = shutil.disk_usage("/")
    p("✅" if free//(1024**3) > 100 else "⚠️", f"Disk: {free//(1024**3)} GB slobodno / {total//(1024**3)} GB")
    
    # ── Direktoriji ──
    print("\n📁 DIREKTORIJI")
    for d in ["data/uploads","data/exports","data/models","data/memory_db","data/rag_db",
              "data/laws","data/logs","data/dpo_datasets","data/backups","data/prompt_cache"]:
        Path(d).mkdir(parents=True, exist_ok=True)
        p("✅", d)
    
    # ── Ovisnosti ──
    print("\n🐍 OVISNOSTI")
    for pkg, desc in [("fastapi","API"),("uvicorn","ASGI"),("openpyxl","Excel"),
                       ("pandas","Tablice"),("PyPDF2","PDF"),("qdrant_client","Qdrant"),("neo4j","Neo4j")]:
        try: importlib.import_module(pkg.lower().replace("-","_")); p("✅", f"{pkg}")
        except: p("❌", f"{pkg} — pip install {pkg}")
    
    print("  Opcionalno:")
    for pkg in ["mlx","mlx_lm","sentence_transformers"]:
        try: importlib.import_module(pkg); p("✅", pkg)
        except: p("⚬", f"{pkg} (nije instalirano)")
    
    # ── Servisi ──
    print("\n🔌 SERVISI")
    for name, url in [("vLLM-MLX","http://127.0.0.1:8080/v1/models"),("Qdrant","http://localhost:6333/collections"),
                       ("Neo4j","http://localhost:7474"),("Nyx API","http://localhost:8000/health")]:
        try:
            urllib.request.urlopen(urllib.request.Request(url), timeout=3)
            p("✅", f"{name} — aktivan")
        except: p("⚬", f"{name} — offline")
    
    # ── Modeli ──
    print("\n🤖 MODELI")
    for name, path in [("Qwen 72B","data/models/qwen-72b-4bit"),("Qwen VL 7B","data/models/qwen-vl-7b-4bit")]:
        d = Path(path)
        if d.exists() and any(d.iterdir()):
            sz = sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / (1024**3)
            p("✅", f"{name} — {sz:.1f} GB")
        else:
            p("⚬", f"{name} — nije preuzet")
    
    # ── Upute ──
    print("\n" + "═" * 60)
    print("  Pokretanje:  make docker-up && make vllm-start && make run")
    print("  Deploy:       sudo make deploy")
    print("  RAG ingest:   python -m scripts.ingest_laws")
    print("═" * 60)

if __name__ == "__main__":
    main()
